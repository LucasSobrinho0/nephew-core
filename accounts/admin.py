from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from accounts.models import User
from common.encryption import build_email_lookup, normalize_email_address


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    model = User
    ordering = ('email',)
    list_display = ('email', 'full_name', 'is_staff', 'is_active')
    search_fields = ('full_name', 'username')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('full_name', 'username', 'email_lookup', 'first_name', 'last_name')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (
            None,
            {
                'classes': ('wide',),
                'fields': ('email', 'full_name', 'password1', 'password2', 'is_staff', 'is_superuser'),
            },
        ),
    )
    readonly_fields = ('email_lookup',)

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)

        if '@' in search_term:
            normalized_email = normalize_email_address(search_term)
            queryset |= self.model.objects.filter(email_lookup=build_email_lookup(normalized_email))

        return queryset, use_distinct
