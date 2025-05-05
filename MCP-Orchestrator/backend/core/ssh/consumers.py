import json
import logging
from uuid import UUID
from channels.generic.websocket import WebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from asgiref.sync import async_to_sync
from django.shortcuts import get_object_or_404

from apps.endpoints.models import Endpoint
from core.ssh.manager import create_connection, get_connection

logger = logging.getLogger(__name__)

class TerminalConsumer(WebsocketConsumer):
    """
    WebSocket consumer for SSH terminal connections.
    
    This consumer handles the WebSocket connection for interactive
    terminal sessions with SSH servers.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ssh_session_id = None
        self.ssh_connection = None
        self.endpoint_id = None
        self.group_name = None
    
    def connect(self):
        """Handle WebSocket connection"""
        # Get user from the scope (set by AuthMiddleware)
        user = self.scope['user']
        
        # Check if the user is authenticated
        if isinstance(user, AnonymousUser):
            logger.warning("Unauthenticated user attempted to connect to terminal")
            self.close(code=4003)
            return
        
        # Extract endpoint_id from URL route
        self.endpoint_id = self.scope['url_route']['kwargs'].get('endpoint_id')
        
        if not self.endpoint_id:
            logger.error("No endpoint ID provided in URL")
            self.close(code=4000)
            return
        
        try:
            # Get the endpoint from the database
            endpoint = get_object_or_404(Endpoint, id=self.endpoint_id)
            
            # Create a new SSH connection
            self.ssh_connection = create_connection(
                endpoint=endpoint,
                user=user,
                client_ip=self.scope.get('client', ('127.0.0.1', 0))[0],
                user_agent=self.scope.get('headers', {}).get('user-agent', b'').decode('utf-8')
            )
            
            # Open the shell and connect to the server
            success = self.ssh_connection.open_shell(
                channel_name=self.channel_name,
                term_width=80,   # Default terminal size
                term_height=24   # Will be resized after connection
            )
            
            if not success:
                logger.error(f"Failed to connect to endpoint {endpoint.name}")
                self.close(code=4001)
                return
            
            # Store the session ID
            self.ssh_session_id = str(self.ssh_connection.session_id)
            
            # Create a group name for this connection
            self.group_name = f"terminal_{self.ssh_session_id}"
            
            # Add to channel group
            async_to_sync(self.channel_layer.group_add)(
                self.group_name,
                self.channel_name
            )
            
            # Accept the connection
            self.accept()
            
            # Send initial connection message
            self.send(text_data=json.dumps({
                'type': 'connection_established',
                'message': f"Connected to {endpoint.name}",
                'session_id': self.ssh_session_id
            }))
            
            logger.info(f"Terminal WebSocket connected for session {self.ssh_session_id}")
            
        except Exception as e:
            logger.error(f"Error connecting to terminal: {str(e)}")
            self.close(code=4002)
    
    def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        logger.info(f"Terminal WebSocket disconnected, code {close_code}, session {self.ssh_session_id}")
        
        try:
            # Remove from group
            if self.group_name:
                async_to_sync(self.channel_layer.group_discard)(
                    self.group_name,
                    self.channel_name
                )
            
            # Disconnect SSH connection
            if self.ssh_connection:
                self.ssh_connection.disconnect()
                self.ssh_connection = None
        
        except Exception as e:
            logger.error(f"Error during WebSocket disconnect: {str(e)}")
    
    def receive(self, text_data):
        """Handle messages received from the WebSocket client"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type', '')
            
            # Handle different message types
            if message_type == 'terminal_input':
                # Send input to the SSH terminal
                if self.ssh_connection:
                    self.ssh_connection.send_input(data.get('data', ''))
            
            elif message_type == 'resize_terminal':
                # Resize the terminal
                if self.ssh_connection:
                    cols = data.get('cols', 80)
                    rows = data.get('rows', 24)
                    self.ssh_connection.resize_terminal(cols, rows)
            
            elif message_type == 'ping':
                # Heartbeat to keep the connection alive
                self.send(text_data=json.dumps({'type': 'pong'}))
            
            else:
                logger.warning(f"Unknown message type: {message_type}")
        
        except json.JSONDecodeError:
            logger.error("Received invalid JSON data")
        
        except Exception as e:
            logger.error(f"Error processing received message: {str(e)}")
    
    def terminal_output(self, event):
        """Handle terminal output messages from the channel layer"""
        try:
            # Forward the terminal output to the WebSocket client
            self.send(text_data=json.dumps({
                'type': 'terminal_output',
                'data': event.get('data', '')
            }))
        
        except Exception as e:
            logger.error(f"Error sending terminal output: {str(e)}")
    
    def terminal_error(self, event):
        """Handle terminal error messages from the channel layer"""
        try:
            # Forward the error message to the WebSocket client
            self.send(text_data=json.dumps({
                'type': 'terminal_error',
                'message': event.get('message', '')
            }))
        
        except Exception as e:
            logger.error(f"Error sending terminal error: {str(e)}")
            
    def _handle_auth_error(self):
        """Helper method to handle authentication errors"""
        self.send(text_data=json.dumps({
            'type': 'terminal_error',
            'message': 'Authentication failed. Please check your credentials and try again.'
        }))
        # Close the connection after a short delay
        self.close(code=4003)