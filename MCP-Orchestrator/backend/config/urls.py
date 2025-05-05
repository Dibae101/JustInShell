from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static
from apps.endpoints.views_dashboard import dashboard

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/endpoints/', include('apps.endpoints.urls')),
    # Other app URLs will be added in future phases
    path('api/agents/', include('apps.agents.urls', namespace='agents')),
    path('api/deployment/', include('apps.deployment.urls', namespace='deployment')),
    path('api/addons/', include('apps.addons.urls', namespace='addons')),
    
    # API authentication
    path('api-auth/', include('rest_framework.urls')),
    
    # Dashboard and terminal UI routes
    path('dashboard/', dashboard, name='dashboard'),
    path('terminals/', include([
        # We'll include these routes directly to have cleaner URLs
        path('', include('apps.endpoints.urls')),
    ])),
    
    # Redirect root to dashboard
    path('', RedirectView.as_view(url='/dashboard/'), name='index'),
]

# Serve static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)