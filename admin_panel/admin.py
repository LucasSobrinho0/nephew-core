from django.contrib import admin

from admin_panel.models import AdminAccessLog


@admin.register(AdminAccessLog)
class AdminAccessLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'ip_address', 'logged_in_at', 'logged_out_at', 'logged_in_by', 'logged_out_by')
    search_fields = ('user__full_name', 'user__username', 'user__email_lookup', 'ip_address', 'session_key')
    list_filter = ('logged_in_at', 'logged_out_at')
    readonly_fields = ('user', 'logged_in_by', 'logged_out_by', 'session_key', 'ip_address', 'user_agent', 'logged_in_at', 'logged_out_at')

