from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views
from . import views_terminal

# Create a router for the API endpoints
router = DefaultRouter()
router.register(r'list', views.EndpointViewSet, basename='api-endpoint')

urlpatterns = [
    # API endpoints
    path('', include(router.urls)),
    
    # Terminal UI routes
    path('', views_terminal.endpoint_list, name='endpoint-list'),
    path('console/<uuid:endpoint_id>/', views_terminal.terminal_console, name='terminal-console'),
    path('test-connection/<uuid:endpoint_id>/', views_terminal.test_endpoint_connection, name='test-connection'),
]