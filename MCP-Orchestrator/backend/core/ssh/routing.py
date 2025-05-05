from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # WebSocket endpoint for terminal connections
    # The endpoint_id is the UUID of the endpoint to connect to
    re_path(r'ws/terminal/(?P<endpoint_id>[0-9a-f-]+)/$', consumers.TerminalConsumer.as_asgi()),
]