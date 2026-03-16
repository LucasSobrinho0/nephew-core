from django.contrib import admin

from integrations.models import AppCatalog, AppCredentialAccessAudit, OrganizationAppCredential, OrganizationAppInstallation


@admin.register(AppCatalog)
class AppCatalogAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'supports_api_key', 'is_active', 'sort_order')
    list_filter = ('supports_api_key', 'is_active')
    search_fields = ('name', 'code')
    ordering = ('sort_order', 'name')


@admin.register(OrganizationAppInstallation)
class OrganizationAppInstallationAdmin(admin.ModelAdmin):
    list_display = ('organization', 'app', 'status', 'created_by', 'updated_by', 'updated_at')
    list_filter = ('status', 'app')
    search_fields = ('organization__name', 'app__name', 'app__code')


@admin.register(OrganizationAppCredential)
class OrganizationAppCredentialAdmin(admin.ModelAdmin):
    list_display = ('installation', 'credential_type', 'status', 'masked_value', 'version', 'updated_at')
    list_filter = ('credential_type', 'status')
    search_fields = ('installation__organization__name', 'installation__app__name', 'masked_value')
    readonly_fields = ('masked_value', 'last_four', 'version')
    exclude = ('secret_value',)


@admin.register(AppCredentialAccessAudit)
class AppCredentialAccessAuditAdmin(admin.ModelAdmin):
    list_display = ('organization', 'app', 'actor', 'event_type', 'outcome', 'reason', 'created_at')
    list_filter = ('event_type', 'outcome')
    search_fields = ('organization__name', 'app__name', 'actor__full_name', 'actor__email_lookup', 'reason')
