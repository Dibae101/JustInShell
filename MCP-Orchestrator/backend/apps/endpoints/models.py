import uuid
import logging
from datetime import datetime, timedelta

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from core.utils.security import encrypt_value, decrypt_value

logger = logging.getLogger(__name__)

class Tag(models.Model):
    """
    Tags for categorizing endpoints
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)
    color = models.CharField(max_length=20, default="#3B82F6")  # Default blue color
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Tag'
        verbose_name_plural = 'Tags'


class EndpointGroup(models.Model):
    """
    Groups for organizing endpoints
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Endpoint Group'
        verbose_name_plural = 'Endpoint Groups'


class Endpoint(models.Model):
    """
    Remote SSH endpoint that can be connected to
    """
    STATUS_CHOICES = [
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('unreachable', 'Unreachable'),
        ('maintenance', 'Maintenance'),
    ]
    
    AUTH_TYPE_CHOICES = [
        ('password', 'Password'),
        ('ssh_key', 'SSH Key'),
        ('ssh_key_with_passphrase', 'SSH Key with Passphrase'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    hostname = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    port = models.IntegerField(default=22)
    username = models.CharField(max_length=100)
    
    # Authentication information - stored encrypted
    auth_type = models.CharField(max_length=50, choices=AUTH_TYPE_CHOICES, default='password')
    password = models.CharField(max_length=255, blank=True, null=True, help_text="Stored encrypted")
    ssh_key = models.TextField(blank=True, null=True, help_text="Private key for SSH authentication")
    ssh_key_passphrase = models.CharField(max_length=255, blank=True, null=True, help_text="Stored encrypted")
    
    # Status information
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offline')
    last_connected = models.DateTimeField(null=True, blank=True)
    last_status_update = models.DateTimeField(null=True, blank=True)
    
    # Additional information
    description = models.TextField(blank=True)
    os_info = models.JSONField(null=True, blank=True)
    
    # Relationships
    groups = models.ManyToManyField(EndpointGroup, blank=True, related_name='endpoints')
    tags = models.ManyToManyField(Tag, blank=True, related_name='endpoints')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.hostname}:{self.port})"
    
    def save(self, *args, **kwargs):
        # Encrypt sensitive data before saving
        is_new = self._state.adding
        
        if self.password:
            self.password = encrypt_value(self.password)
        
        if self.ssh_key_passphrase:
            self.ssh_key_passphrase = encrypt_value(self.ssh_key_passphrase)
            
        # Update last_status_update when status changes
        if not is_new and self.status != Endpoint.objects.get(pk=self.pk).status:
            self.last_status_update = timezone.now()
            
        super().save(*args, **kwargs)
    
    def get_password(self):
        """Decrypt and return the password"""
        if self.password:
            return decrypt_value(self.password)
        return None
    
    def get_ssh_key_passphrase(self):
        """Decrypt and return the SSH key passphrase"""
        if self.ssh_key_passphrase:
            return decrypt_value(self.ssh_key_passphrase)
        return None
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Endpoint'
        verbose_name_plural = 'Endpoints'
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['hostname']),
            models.Index(fields=['ip_address']),
        ]


class SSHSession(models.Model):
    """
    Record of an SSH session to an endpoint
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    endpoint = models.ForeignKey(Endpoint, on_delete=models.CASCADE, related_name='sessions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ssh_sessions')
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    connection_log = models.TextField(blank=True)
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    
    @property
    def duration(self):
        """Calculate the duration of the session"""
        if self.ended_at:
            return self.ended_at - self.started_at
        elif self.is_active:
            return timezone.now() - self.started_at
        return None
    
    @property
    def commands_count(self):
        """Return the number of commands executed in this session"""
        return self.commands.count()
    
    def end_session(self):
        """End the SSH session"""
        self.is_active = False
        self.ended_at = timezone.now()
        self.save(update_fields=['is_active', 'ended_at'])
    
    def __str__(self):
        return f"Session {self.id} - {self.endpoint.name} by {self.user.username}"
    
    class Meta:
        ordering = ['-started_at']
        verbose_name = 'SSH Session'
        verbose_name_plural = 'SSH Sessions'
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['started_at']),
        ]


class SSHCommand(models.Model):
    """
    Record of a command executed during an SSH session
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(SSHSession, on_delete=models.CASCADE, related_name='commands')
    command = models.TextField()
    output = models.TextField(blank=True)
    exit_code = models.IntegerField(null=True, blank=True)
    executed_at = models.DateTimeField(auto_now_add=True)
    duration = models.DurationField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.command[:50]}{'...' if len(self.command) > 50 else ''}"
    
    class Meta:
        ordering = ['executed_at']
        verbose_name = 'SSH Command'
        verbose_name_plural = 'SSH Commands'