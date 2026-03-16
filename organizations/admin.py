from django.contrib import admin

from organizations.models import Organization, OrganizationInvite, OrganizationMembership


class OrganizationMembershipInline(admin.TabularInline):
    model = OrganizationMembership
    extra = 0


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'segment', 'team_size', 'is_active', 'created_at')
    list_filter = ('segment', 'team_size', 'is_active')
    search_fields = ('name', 'slug')
    inlines = (OrganizationMembershipInline,)


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ('organization', 'user', 'role', 'is_active', 'created_at')
    list_filter = ('role', 'is_active')
    search_fields = ('organization__name', 'user__email', 'user__full_name')


@admin.register(OrganizationInvite)
class OrganizationInviteAdmin(admin.ModelAdmin):
    list_display = ('code', 'organization', 'target_role', 'status', 'created_by', 'created_at', 'expires_at')
    list_filter = ('target_role', 'status')
    search_fields = ('code', 'organization__name', 'created_by__email')
