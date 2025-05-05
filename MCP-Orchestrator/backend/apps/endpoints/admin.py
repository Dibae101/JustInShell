from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from apps.endpoints.models import Endpoint, EndpointGroup, Tag, SSHSession, SSHCommand

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'color_display', 'description', 'created_by', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')
    
    def color_display(self, obj):
        return format_html(
            '<span style="background-color: {}; color: #fff; padding: 3px 10px; border-radius: 3px;">{}</span>',
            obj.color, obj.color
        )
    color_display.short_description = _('Color')


@admin.register(EndpointGroup)
class EndpointGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'description', 'endpoints_count', 'created_by', 'created_at')
    search_fields = ('name', 'description')
    list_filter = ('created_at', 'parent')
    readonly_fields = ('created_at', 'updated_at')
    
    def endpoints_count(self, obj):
        return obj.endpoints.count()
    endpoints_count.short_description = _('Endpoints')


class EndpointTagInline(admin.TabularInline):
    model = Endpoint.tags.through
    extra = 1
    verbose_name = _("Tag")
    verbose_name_plural = _("Tags")


class EndpointGroupInline(admin.TabularInline):
    model = Endpoint.groups.through
    extra = 1
    verbose_name = _("Group")
    verbose_name_plural = _("Groups")


@admin.register(Endpoint)
class EndpointAdmin(admin.ModelAdmin):
    list_display = ('name', 'hostname', 'ip_address', 'port', 'username', 'status_display', 
                   'auth_type', 'last_connected', 'created_by')
    search_fields = ('name', 'hostname', 'ip_address', 'username', 'description')
    list_filter = ('status', 'auth_type', 'port', 'groups', 'tags', 'created_at')
    readonly_fields = ('last_connected', 'last_status_update', 'created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('name', 'hostname', 'ip_address', 'port', 'username', 'description')
        }),
        (_('Authentication'), {
            'fields': ('auth_type', 'password', 'ssh_key', 'ssh_key_passphrase'),
            'classes': ('collapse',),
        }),
        (_('Status'), {
            'fields': ('status', 'last_connected', 'last_status_update'),
        }),
        (_('System Information'), {
            'fields': ('os_info',),
            'classes': ('collapse',),
        }),
        (_('Metadata'), {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    exclude = ('_password', '_ssh_key', '_ssh_key_passphrase', 'groups', 'tags')
    inlines = [EndpointGroupInline, EndpointTagInline]
    
    def status_display(self, obj):
        status_colors = {
            'online': 'green',
            'offline': 'gray',
            'unreachable': 'red',
            'maintenance': 'orange',
        }
        color = status_colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: white; background-color: {}; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color, obj.get_status_display()
        )
    status_display.short_description = _('Status')
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating a new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class SSHCommandInline(admin.TabularInline):
    model = SSHCommand
    readonly_fields = ('command', 'output', 'exit_code', 'executed_at', 'duration')
    extra = 0
    can_delete = False
    max_num = 0
    verbose_name = _("Command")
    verbose_name_plural = _("Commands")


@admin.register(SSHSession)
class SSHSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'endpoint', 'user', 'started_at', 'session_duration', 
                   'is_active', 'commands_count', 'client_ip')
    list_filter = ('is_active', 'started_at', 'endpoint', 'user')
    search_fields = ('id', 'endpoint__name', 'endpoint__hostname', 'user__username', 'client_ip')
    readonly_fields = ('id', 'endpoint', 'user', 'started_at', 'ended_at', 'is_active', 
                       'connection_log', 'client_ip', 'user_agent', 'session_duration')
    inlines = [SSHCommandInline]
    
    def session_duration(self, obj):
        duration = obj.duration
        if duration:
            return str(duration).split('.')[0]  # Remove microseconds
        return '-'
    session_duration.short_description = _('Duration')
    
    def has_add_permission(self, request):
        return False


@admin.register(SSHCommand)
class SSHCommandAdmin(admin.ModelAdmin):
    list_display = ('command', 'session', 'exit_code', 'executed_at', 'command_duration')
    list_filter = ('executed_at', 'exit_code', 'session__endpoint', 'session__user')
    search_fields = ('command', 'output', 'session__id', 'session__endpoint__name')
    readonly_fields = ('session', 'command', 'output', 'exit_code', 'executed_at', 'duration')
    
    def command_duration(self, obj):
        if obj.duration:
            return str(obj.duration).split('.')[0]  # Remove microseconds
        return '-'
    command_duration.short_description = _('Duration')
    
    def has_add_permission(self, request):
        return False