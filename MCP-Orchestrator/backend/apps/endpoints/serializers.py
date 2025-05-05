from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Tag, EndpointGroup, Endpoint, SSHSession, SSHCommand

User = get_user_model()


class TagSerializer(serializers.ModelSerializer):
    """Serializer for endpoint tags"""
    class Meta:
        model = Tag
        fields = ['id', 'name', 'color', 'created_by', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def create(self, validated_data):
        """Create a new tag and assign current user"""
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class EndpointGroupSerializer(serializers.ModelSerializer):
    """Serializer for endpoint groups"""
    endpoint_count = serializers.SerializerMethodField()
    
    class Meta:
        model = EndpointGroup
        fields = ['id', 'name', 'description', 'created_by', 'created_at', 'updated_at', 'endpoint_count']
        read_only_fields = ['id', 'created_at', 'updated_at', 'endpoint_count']
    
    def get_endpoint_count(self, obj):
        """Get the count of endpoints in this group"""
        return obj.endpoints.count()
    
    def create(self, validated_data):
        """Create a new group and assign current user"""
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class EndpointListSerializer(serializers.ModelSerializer):
    """Serializer for listing endpoints (without sensitive data)"""
    groups = serializers.StringRelatedField(many=True)
    tags = TagSerializer(many=True, read_only=True)
    created_by = serializers.StringRelatedField()
    
    class Meta:
        model = Endpoint
        fields = [
            'id', 'name', 'hostname', 'ip_address', 'port', 'username', 
            'auth_type', 'status', 'last_connected', 'last_status_update',
            'description', 'os_info', 'groups', 'tags', 'created_by', 
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'status', 'last_connected', 'last_status_update',
            'os_info', 'created_at', 'updated_at'
        ]


class EndpointDetailSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating endpoints (with sensitive data)"""
    groups = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=EndpointGroup.objects.all(),
        required=False
    )
    tags = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Tag.objects.all(),
        required=False
    )
    
    class Meta:
        model = Endpoint
        fields = [
            'id', 'name', 'hostname', 'ip_address', 'port', 'username', 
            'auth_type', 'password', 'ssh_key', 'ssh_key_passphrase',
            'status', 'last_connected', 'last_status_update',
            'description', 'os_info', 'groups', 'tags', 'created_by', 
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'status', 'last_connected', 'last_status_update',
            'os_info', 'created_by', 'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'password': {'write_only': True},
            'ssh_key_passphrase': {'write_only': True},
        }
    
    def create(self, validated_data):
        """Create a new endpoint and assign current user"""
        groups = validated_data.pop('groups', [])
        tags = validated_data.pop('tags', [])
        
        # Assign the current user
        validated_data['created_by'] = self.context['request'].user
        
        # Create the endpoint
        endpoint = Endpoint.objects.create(**validated_data)
        
        # Add groups and tags
        if groups:
            endpoint.groups.set(groups)
        if tags:
            endpoint.tags.set(tags)
        
        return endpoint
    
    def update(self, instance, validated_data):
        """Update endpoint with sensitive data handling"""
        groups = validated_data.pop('groups', None)
        tags = validated_data.pop('tags', None)
        
        # Update groups and tags if provided
        if groups is not None:
            instance.groups.set(groups)
        if tags is not None:
            instance.tags.set(tags)
        
        # Special handling for password and passphrase
        # Only update them if they are provided
        password = validated_data.pop('password', None)
        ssh_key_passphrase = validated_data.pop('ssh_key_passphrase', None)
        
        # Update the remaining fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Update password and passphrase if provided
        if password is not None:
            instance.password = password
        if ssh_key_passphrase is not None:
            instance.ssh_key_passphrase = ssh_key_passphrase
        
        instance.save()
        return instance


class SSHCommandSerializer(serializers.ModelSerializer):
    """Serializer for SSH commands"""
    class Meta:
        model = SSHCommand
        fields = ['id', 'command', 'output', 'exit_code', 'executed_at', 'duration']
        read_only_fields = ['id', 'executed_at']


class SSHSessionListSerializer(serializers.ModelSerializer):
    """Serializer for listing SSH sessions"""
    endpoint_name = serializers.ReadOnlyField(source='endpoint.name')
    username = serializers.ReadOnlyField(source='user.username')
    duration_str = serializers.SerializerMethodField()
    
    class Meta:
        model = SSHSession
        fields = [
            'id', 'endpoint', 'endpoint_name', 'user', 'username',
            'started_at', 'ended_at', 'is_active', 'duration_str',
            'commands_count', 'client_ip', 'user_agent'
        ]
        read_only_fields = fields
    
    def get_duration_str(self, obj):
        """Return the session duration as a human-readable string"""
        duration = obj.duration
        if duration:
            seconds = duration.total_seconds()
            hours, remainder = divmod(seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            # Format as HH:MM:SS
            return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
        return "N/A"


class SSHSessionDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed SSH session information"""
    endpoint = EndpointListSerializer(read_only=True)
    commands = SSHCommandSerializer(many=True, read_only=True)
    username = serializers.ReadOnlyField(source='user.username')
    
    class Meta:
        model = SSHSession
        fields = [
            'id', 'endpoint', 'user', 'username', 'started_at', 'ended_at',
            'is_active', 'duration', 'connection_log', 'client_ip',
            'user_agent', 'commands'
        ]
        read_only_fields = fields


class TestConnectionSerializer(serializers.Serializer):
    """Serializer for testing SSH connections"""
    hostname = serializers.CharField(max_length=255)
    port = serializers.IntegerField(default=22)
    username = serializers.CharField(max_length=100)
    auth_type = serializers.ChoiceField(
        choices=Endpoint.AUTH_TYPE_CHOICES,
        default='password'
    )
    password = serializers.CharField(
        max_length=255, 
        required=False,
        allow_blank=True
    )
    ssh_key = serializers.CharField(
        required=False,
        allow_blank=True
    )
    ssh_key_passphrase = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True
    )


class ExecuteCommandSerializer(serializers.Serializer):
    """Serializer for executing commands on endpoints"""
    command = serializers.CharField()
    endpoint_id = serializers.UUIDField()