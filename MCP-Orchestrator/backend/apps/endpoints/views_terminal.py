from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Endpoint, EndpointGroup, Tag, SSHSession
from .serializers import SSHSessionDetailSerializer
from core.ssh.manager import test_connection, create_connection

@login_required
def endpoint_list(request):
    """
    Display a list of available endpoints for SSH terminal access
    """
    # Get all endpoints
    endpoints = Endpoint.objects.all().order_by('name')
    
    # Get groups for filtering
    groups = EndpointGroup.objects.all().order_by('name')
    
    # Get tags for filtering
    tags = Tag.objects.all().order_by('name')
    
    context = {
        'endpoints': endpoints,
        'groups': groups,
        'tags': tags,
    }
    
    return render(request, 'terminal/endpoint_list.html', context)

@login_required
def terminal_console(request, endpoint_id):
    """
    Display the SSH terminal console for a specific endpoint
    """
    # Get the endpoint or return 404
    endpoint = get_object_or_404(Endpoint, id=endpoint_id)
    
    # Create a new session when viewing the console
    # The actual SSH connection will be established by the WebSocket consumer
    session = SSHSession(
        endpoint=endpoint,
        user=request.user,
        is_active=True,
        client_ip=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )
    session.save()
    
    # Create the WebSocket URL
    ws_scheme = 'wss' if request.is_secure() else 'ws'
    ws_url = f"{ws_scheme}://{request.get_host()}/ws/ssh/{endpoint_id}/"
    
    context = {
        'endpoint': endpoint,
        'session': session,
        'ws_url': ws_url,
    }
    
    return render(request, 'terminal/console.html', context)

@login_required
def test_endpoint_connection(request, endpoint_id):
    """
    API endpoint to test the SSH connection to an endpoint
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)
    
    # Get the endpoint or return 404
    endpoint = get_object_or_404(Endpoint, id=endpoint_id)
    
    # Test the connection
    success, message = test_connection(endpoint)
    
    # Update the endpoint status
    status = 'online' if success else 'unreachable'
    endpoint.update_status(status)
    
    return JsonResponse({
        'success': success,
        'message': message,
        'status': status,
        'last_check': timezone.now().isoformat()
    })


class TerminalViewSet(viewsets.ViewSet):
    """ViewSet for terminal operations"""
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['post'])
    def start_session(self, request):
        """Start a new terminal session with an endpoint"""
        endpoint_id = request.data.get('endpoint_id')
        
        # Validate the endpoint exists
        try:
            endpoint = Endpoint.objects.get(id=endpoint_id)
        except Endpoint.DoesNotExist:
            return Response({
                'error': 'Endpoint not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Create a new SSH connection
        ssh_connection = create_connection(
            endpoint=endpoint,
            user=request.user,
            client_ip=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT')
        )
        
        # Try to connect
        if ssh_connection.connect():
            # Return the session ID for the WebSocket connection
            return Response({
                'session_id': str(ssh_connection.session.id),
                'endpoint': {
                    'id': str(endpoint.id),
                    'name': endpoint.name,
                    'hostname': endpoint.hostname
                }
            })
        else:
            return Response({
                'error': 'Failed to connect to the endpoint',
                'details': ssh_connection.session.connection_log if ssh_connection.session else None
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    
    @action(detail=False, methods=['post'])
    def end_session(self, request):
        """End an active terminal session"""
        session_id = request.data.get('session_id')
        
        # Validate the session exists and belongs to the current user
        try:
            session = SSHSession.objects.get(
                id=session_id,
                user=request.user,
                is_active=True
            )
        except SSHSession.DoesNotExist:
            return Response({
                'error': 'Active session not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # End the session
        session.end_session()
        
        return Response({
            'message': 'Session terminated successfully'
        })
    
    @action(detail=False, methods=['get'])
    def active_sessions(self, request):
        """Get all active terminal sessions for the current user"""
        sessions = SSHSession.objects.filter(
            user=request.user,
            is_active=True
        ).select_related('endpoint')
        
        sessions_data = []
        for session in sessions:
            sessions_data.append({
                'id': str(session.id),
                'endpoint': {
                    'id': str(session.endpoint.id),
                    'name': session.endpoint.name,
                    'hostname': session.endpoint.hostname
                },
                'started_at': session.started_at,
                'duration': session.duration
            })
        
        return Response(sessions_data)


class TerminalStatusView(APIView):
    """View for checking terminal service status"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get the status of the terminal service"""
        return Response({
            'status': 'active',
            'service': 'terminal',
            'timestamp': timezone.now()
        })