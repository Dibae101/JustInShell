from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count
from django.utils import timezone

from .models import Endpoint, EndpointGroup, Tag, SSHSession
from .serializers import (
    EndpointListSerializer, EndpointDetailSerializer,
    EndpointGroupSerializer, TagSerializer,
    SSHSessionListSerializer, SSHSessionDetailSerializer,
    TestConnectionSerializer, ExecuteCommandSerializer
)
from core.ssh.manager import test_connection, create_connection


class EndpointViewSet(viewsets.ModelViewSet):
    """ViewSet for managing server endpoints"""
    permission_classes = [permissions.IsAuthenticated]
    queryset = Endpoint.objects.all()
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action in ['create', 'update', 'partial_update']:
            return EndpointDetailSerializer
        return EndpointListSerializer
    
    def get_queryset(self):
        """Filter endpoints based on query parameters"""
        queryset = Endpoint.objects.all().prefetch_related('groups', 'tags')
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by group
        group_id = self.request.query_params.get('group')
        if group_id:
            queryset = queryset.filter(groups__id=group_id)
        
        # Filter by tag
        tag_id = self.request.query_params.get('tag')
        if tag_id:
            queryset = queryset.filter(tags__id=tag_id)
        
        # Search by name, hostname, or description
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(hostname__icontains=search) | 
                Q(description__icontains=search)
            )
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """Test connection to an endpoint"""
        endpoint = self.get_object()
        success, message = test_connection(endpoint)
        
        if success:
            # Update the endpoint status
            endpoint.status = 'online'
            endpoint.last_status_update = timezone.now()
            endpoint.save(update_fields=['status', 'last_status_update'])
        
        return Response({
            'success': success,
            'message': message
        })
    
    @action(detail=False, methods=['post'])
    def test_credentials(self, request):
        """Test connection without saving the endpoint"""
        serializer = TestConnectionSerializer(data=request.data)
        if serializer.is_valid():
            # Create a temporary endpoint object
            temp_endpoint = Endpoint(**serializer.validated_data)
            
            # Test the connection
            success, message = test_connection(temp_endpoint)
            
            return Response({
                'success': success,
                'message': message
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def execute_command(self, request, pk=None):
        """Execute a single command on an endpoint"""
        serializer = ExecuteCommandSerializer(data=request.data)
        if serializer.is_valid():
            endpoint = self.get_object()
            command = serializer.validated_data['command']
            
            # Create a connection
            ssh_connection = create_connection(
                endpoint=endpoint,
                user=request.user,
                client_ip=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT')
            )
            
            # Connect and execute the command
            if ssh_connection.connect():
                stdout, stderr, exit_code = ssh_connection.execute_command(command)
                
                # Disconnect after the command
                ssh_connection.disconnect()
                
                return Response({
                    'command': command,
                    'stdout': stdout,
                    'stderr': stderr,
                    'exit_code': exit_code
                })
            else:
                return Response({
                    'error': 'Could not connect to the endpoint'
                }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EndpointGroupViewSet(viewsets.ModelViewSet):
    """ViewSet for managing endpoint groups"""
    permission_classes = [permissions.IsAuthenticated]
    queryset = EndpointGroup.objects.all()
    serializer_class = EndpointGroupSerializer
    
    def get_queryset(self):
        """Custom queryset to include endpoint count"""
        return EndpointGroup.objects.annotate(
            count=Count('endpoints')
        ).order_by('name')


class TagViewSet(viewsets.ModelViewSet):
    """ViewSet for managing endpoint tags"""
    permission_classes = [permissions.IsAuthenticated]
    queryset = Tag.objects.all()
    serializer_class = TagSerializer


class SSHSessionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing SSH sessions"""
    permission_classes = [permissions.IsAuthenticated]
    queryset = SSHSession.objects.all()
    
    def get_queryset(self):
        """Filter sessions based on query parameters"""
        queryset = SSHSession.objects.all().select_related('endpoint', 'user')
        
        # Filter by active status
        is_active = self.request.query_params.get('active')
        if is_active is not None:
            is_active = is_active.lower() == 'true'
            queryset = queryset.filter(is_active=is_active)
        
        # Filter by endpoint
        endpoint_id = self.request.query_params.get('endpoint')
        if endpoint_id:
            queryset = queryset.filter(endpoint_id=endpoint_id)
        
        # Filter by user (default to current user)
        user_id = self.request.query_params.get('user')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        # Order by most recent first
        return queryset.order_by('-started_at')
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'retrieve':
            return SSHSessionDetailSerializer
        return SSHSessionListSerializer
    
    @action(detail=True, methods=['post'])
    def terminate(self, request, pk=None):
        """Terminate an active SSH session"""
        session = self.get_object()
        
        if not session.is_active:
            return Response({
                'error': 'Session is already terminated'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # End the session
        session.end_session()
        
        return Response({
            'message': 'Session terminated successfully'
        })