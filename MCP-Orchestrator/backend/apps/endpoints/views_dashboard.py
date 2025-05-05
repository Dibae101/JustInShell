from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Endpoint, SSHSession, SSHCommand
from apps.agents.models import Agent
from apps.deployment.models import Deployment


class DashboardViewSet(viewsets.ViewSet):
    """ViewSet for dashboard operations"""
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get statistical data for the dashboard"""
        # Get counts of various entities
        endpoint_count = Endpoint.objects.count()
        agent_count = Agent.objects.count()
        deployment_count = Deployment.objects.count()
        
        # Get active sessions
        active_sessions = SSHSession.objects.filter(is_active=True).count()
        
        # Get recent activity (sessions in the last 24 hours)
        last_24h = timezone.now() - timedelta(hours=24)
        recent_sessions = SSHSession.objects.filter(started_at__gte=last_24h).count()
        
        # Get endpoint status summary
        endpoints_by_status = Endpoint.objects.values('status').annotate(
            count=Count('id')
        )
        
        status_summary = {}
        for item in endpoints_by_status:
            status_summary[item['status']] = item['count']
        
        return Response({
            'endpoints': {
                'total': endpoint_count,
                'status': status_summary
            },
            'agents': {
                'total': agent_count
            },
            'deployments': {
                'total': deployment_count
            },
            'sessions': {
                'active': active_sessions,
                'recent': recent_sessions
            },
            'timestamp': timezone.now()
        })

    @action(detail=False, methods=['get'])
    def activity(self, request):
        """Get recent activity for the dashboard"""
        # Get recent sessions (last 7 days)
        last_week = timezone.now() - timedelta(days=7)
        
        recent_sessions = SSHSession.objects.filter(
            started_at__gte=last_week
        ).select_related('user', 'endpoint').order_by('-started_at')[:10]
        
        activity_data = []
        for session in recent_sessions:
            activity_data.append({
                'id': str(session.id),
                'type': 'terminal_session',
                'user': session.user.username,
                'endpoint': session.endpoint.name,
                'timestamp': session.started_at,
                'duration': session.duration,
                'is_active': session.is_active
            })
        
        return Response(activity_data)


def dashboard_view(request):
    """Render the dashboard HTML view"""
    return render(request, 'dashboard/index.html')