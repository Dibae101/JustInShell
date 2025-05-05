import os
import io
import time
import uuid
import logging
import threading
import paramiko
from django.conf import settings
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from apps.endpoints.models import Endpoint, SSHSession, SSHCommand

logger = logging.getLogger(__name__)

# Dictionary to store active SSH connections
active_connections = {}

class SSHConnection:
    """
    Manages an SSH connection to a remote server.
    
    This class handles creating, maintaining, and closing SSH connections,
    as well as executing commands and managing interactive shells.
    """
    def __init__(self, endpoint, user, client_ip=None, user_agent=None):
        """
        Initialize a new SSH connection.
        
        Args:
            endpoint (Endpoint): The endpoint to connect to
            user (User): The Django user initiating the connection
            client_ip (str, optional): Client IP address
            user_agent (str, optional): Client user agent
        """
        self.endpoint = endpoint
        self.user = user
        self.client_ip = client_ip
        self.user_agent = user_agent
        
        # SSH connection objects
        self.client = None
        self.shell = None
        self.transport = None
        
        # Session tracking
        self.session = None
        self.session_id = None
        self.is_connected = False
        self.last_activity = time.time()
        
        # Channel for WebSocket communication
        self.channel_name = None
        self.channel_layer = get_channel_layer()
    
    def connect(self):
        """
        Establish an SSH connection to the endpoint
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        if self.is_connected:
            return True
        
        try:
            # Create a new SSH client
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Prepare connection parameters
            connect_kwargs = {
                'hostname': self.endpoint.hostname,
                'port': self.endpoint.port,
                'username': self.endpoint.username,
                'timeout': 10,
            }
            
            # Add authentication based on auth type
            if self.endpoint.auth_type == 'password':
                connect_kwargs['password'] = self.endpoint.get_password()
            
            elif self.endpoint.auth_type in ['ssh_key', 'ssh_key_with_passphrase']:
                # Create in-memory file-like object for the key
                key_file = io.StringIO(self.endpoint.ssh_key)
                
                # Load the key (with passphrase if needed)
                if self.endpoint.auth_type == 'ssh_key_with_passphrase':
                    private_key = paramiko.RSAKey.from_private_key(
                        key_file, 
                        password=self.endpoint.get_ssh_key_passphrase()
                    )
                else:
                    private_key = paramiko.RSAKey.from_private_key(key_file)
                
                connect_kwargs['pkey'] = private_key
            
            # Attempt to connect
            connection_log = f"Connecting to {self.endpoint.hostname}:{self.endpoint.port} as {self.endpoint.username}...\n"
            self.client.connect(**connect_kwargs)
            
            # Update connection status
            self.is_connected = True
            self.transport = self.client.get_transport()
            connection_log += f"Connected successfully at {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            # Create database session record
            self.session = SSHSession.objects.create(
                endpoint=self.endpoint,
                user=self.user,
                is_active=True,
                connection_log=connection_log,
                client_ip=self.client_ip,
                user_agent=self.user_agent
            )
            self.session_id = self.session.id
            
            # Update endpoint status
            self.endpoint.status = 'online'
            self.endpoint.last_connected = timezone.now()
            self.endpoint.save(update_fields=['status', 'last_connected'])
            
            # Add to active connections
            active_connections[str(self.session_id)] = self
            
            return True
        
        except Exception as e:
            error_msg = f"Error connecting to {self.endpoint.hostname}: {str(e)}"
            logger.error(error_msg)
            
            # Create failed session record
            connection_log = f"Connection attempt failed: {error_msg}\n"
            self.session = SSHSession.objects.create(
                endpoint=self.endpoint,
                user=self.user,
                is_active=False,
                connection_log=connection_log,
                client_ip=self.client_ip,
                user_agent=self.user_agent
            )
            
            # Update endpoint status
            self.endpoint.status = 'unreachable' 
            self.endpoint.last_status_update = timezone.now()
            self.endpoint.save(update_fields=['status', 'last_status_update'])
            
            return False
    
    def open_shell(self, channel_name, term_width=80, term_height=24):
        """
        Open an interactive shell session
        
        Args:
            channel_name (str): WebSocket channel name for communication
            term_width (int): Terminal width in characters
            term_height (int): Terminal height in rows
            
        Returns:
            bool: True if shell was successfully opened
        """
        if not self.is_connected:
            if not self.connect():
                return False
        
        try:
            # Store the channel name for later communication
            self.channel_name = channel_name
            
            # Request an interactive shell from the SSH server
            self.shell = self.client.invoke_shell(
                term='xterm-256color',
                width=term_width,
                height=term_height
            )
            
            # Set non-blocking mode
            self.shell.setblocking(0)
            
            # Start a thread to read output from the shell
            thread = threading.Thread(target=self._read_shell_output)
            thread.daemon = True
            thread.start()
            
            return True
        
        except Exception as e:
            error_msg = f"Error opening shell: {str(e)}"
            logger.error(error_msg)
            
            # Update session log
            if self.session:
                self.session.connection_log += f"\n{error_msg}\n"
                self.session.save(update_fields=['connection_log'])
            
            return False
    
    def _read_shell_output(self):
        """
        Read output from the shell in a separate thread
        and send it to the WebSocket channel
        """
        try:
            while self.is_connected and self.shell:
                # Check if there's data to read (non-blocking)
                if self.shell.recv_ready():
                    output = self.shell.recv(4096).decode('utf-8', errors='replace')
                    if output:
                        # Send output to WebSocket
                        self._send_output(output)
                
                # Sleep briefly to prevent CPU hogging
                time.sleep(0.01)
        
        except Exception as e:
            logger.error(f"Error reading shell output: {str(e)}")
            self.disconnect()
    
    def _send_output(self, output):
        """Send output to the WebSocket channel"""
        try:
            if self.channel_name and self.channel_layer:
                async_to_sync(self.channel_layer.send)(
                    self.channel_name,
                    {
                        "type": "terminal.output",
                        "data": output
                    }
                )
        except Exception as e:
            logger.error(f"Error sending output to WebSocket: {str(e)}")
    
    def send_input(self, data):
        """
        Send input to the shell
        
        Args:
            data (str): Input data to send
        """
        if not self.is_connected or not self.shell:
            return
        
        try:
            self.shell.send(data)
            self.last_activity = time.time()
        except Exception as e:
            logger.error(f"Error sending input to shell: {str(e)}")
            self.disconnect()
    
    def resize_terminal(self, width, height):
        """
        Resize the terminal
        
        Args:
            width (int): New terminal width in characters
            height (int): New terminal height in rows
        """
        if not self.is_connected or not self.shell:
            return
        
        try:
            self.shell.resize_pty(width=width, height=height)
        except Exception as e:
            logger.error(f"Error resizing terminal: {str(e)}")
    
    def execute_command(self, command):
        """
        Execute a command on the remote server
        
        Args:
            command (str): Command to execute
            
        Returns:
            tuple: (stdout, stderr, exit_code)
        """
        if not self.is_connected:
            if not self.connect():
                return None, "Not connected to server", -1
        
        try:
            # Record the start time for calculating duration
            start_time = time.time()
            
            # Execute the command
            stdin, stdout, stderr = self.client.exec_command(command)
            
            # Read output
            stdout_data = stdout.read().decode('utf-8', errors='replace')
            stderr_data = stderr.read().decode('utf-8', errors='replace')
            exit_status = stdout.channel.recv_exit_status()
            
            # Calculate duration
            duration = time.time() - start_time
            
            # Log the command in the database
            if self.session:
                SSHCommand.objects.create(
                    session=self.session,
                    command=command,
                    output=stdout_data + (f"\nStderr:\n{stderr_data}" if stderr_data else ""),
                    exit_code=exit_status,
                    duration=timezone.timedelta(seconds=duration)
                )
            
            # Update last activity timestamp
            self.last_activity = time.time()
            
            return stdout_data, stderr_data, exit_status
        
        except Exception as e:
            error_msg = f"Error executing command: {str(e)}"
            logger.error(error_msg)
            
            # Log the failed command
            if self.session:
                SSHCommand.objects.create(
                    session=self.session,
                    command=command,
                    output=f"Error: {error_msg}",
                    exit_code=-1
                )
            
            return None, error_msg, -1
    
    def disconnect(self):
        """Close the SSH connection and clean up resources"""
        try:
            # Close shell
            if self.shell:
                self.shell.close()
                self.shell = None
            
            # Close SSH client
            if self.client:
                self.client.close()
                self.client = None
            
            # Mark as disconnected
            self.is_connected = False
            
            # End the session in the database
            if self.session and self.session.is_active:
                self.session.end_session()
                
                # Update connection log
                self.session.connection_log += f"\nDisconnected at {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}"
                self.session.save(update_fields=['connection_log'])
            
            # Remove from active connections
            if str(self.session_id) in active_connections:
                del active_connections[str(self.session_id)]
        
        except Exception as e:
            logger.error(f"Error during disconnect: {str(e)}")


def get_connection(session_id):
    """
    Get an active SSH connection by session ID
    
    Args:
        session_id (str): Session ID
        
    Returns:
        SSHConnection or None
    """
    return active_connections.get(str(session_id))


def create_connection(endpoint, user, client_ip=None, user_agent=None):
    """
    Create a new SSH connection
    
    Args:
        endpoint (Endpoint): Endpoint to connect to
        user (User): Django user initiating the connection
        client_ip (str, optional): Client IP address
        user_agent (str, optional): Client user agent
        
    Returns:
        SSHConnection: The new connection object
    """
    connection = SSHConnection(endpoint, user, client_ip, user_agent)
    return connection


def test_connection(endpoint):
    """
    Test an SSH connection to verify endpoint credentials
    
    Args:
        endpoint (Endpoint): Endpoint to test
        
    Returns:
        tuple: (success, message)
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        # Prepare connection parameters
        connect_kwargs = {
            'hostname': endpoint.hostname,
            'port': endpoint.port,
            'username': endpoint.username,
            'timeout': 5,  # Short timeout for testing
        }
        
        # Add authentication based on auth type
        if endpoint.auth_type == 'password':
            connect_kwargs['password'] = endpoint.get_password()
        
        elif endpoint.auth_type in ['ssh_key', 'ssh_key_with_passphrase']:
            # Create in-memory file-like object for the key
            key_file = io.StringIO(endpoint.ssh_key)
            
            # Load the key (with passphrase if needed)
            if endpoint.auth_type == 'ssh_key_with_passphrase':
                private_key = paramiko.RSAKey.from_private_key(
                    key_file, 
                    password=endpoint.get_ssh_key_passphrase()
                )
            else:
                private_key = paramiko.RSAKey.from_private_key(key_file)
            
            connect_kwargs['pkey'] = private_key
        
        # Attempt to connect
        client.connect(**connect_kwargs)
        
        # Test if we can execute a simple command
        stdin, stdout, stderr = client.exec_command('echo "Connection test successful"')
        result = stdout.read().decode('utf-8').strip()
        
        # Update endpoint info
        try:
            # Get OS info
            stdin, stdout, stderr = client.exec_command('uname -a')
            os_info = stdout.read().decode('utf-8').strip()
            
            # Store the info
            endpoint.os_info = {
                'uname': os_info
            }
        except:
            # Not critical, so just log and continue
            logger.warning(f"Could not get OS info for {endpoint.hostname}")
        
        # Close the connection
        client.close()
        
        return True, "Connection successful"
    
    except paramiko.AuthenticationException:
        return False, "Authentication failed. Please check your credentials."
    
    except paramiko.SSHException as e:
        return False, f"SSH error: {str(e)}"
    
    except Exception as e:
        return False, f"Connection error: {str(e)}"
    
    finally:
        try:
            client.close()
        except:
            pass


def close_inactive_connections(timeout=3600):
    """
    Close SSH connections that have been inactive for a while
    
    Args:
        timeout (int): Timeout in seconds (default: 1 hour)
    """
    current_time = time.time()
    sessions_to_close = []
    
    for session_id, connection in active_connections.items():
        if current_time - connection.last_activity > timeout:
            # Add to the list of sessions to close
            sessions_to_close.append(session_id)
    
    # Close the inactive sessions
    for session_id in sessions_to_close:
        if session_id in active_connections:
            connection = active_connections[session_id]
            logger.info(f"Closing inactive SSH session {session_id}")
            connection.disconnect()