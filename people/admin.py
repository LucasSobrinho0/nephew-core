from django.contrib import admin

from people.models import Person


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'organization', 'phone', 'is_active', 'created_at')
    list_filter = ('organization', 'is_active')
    search_fields = ('first_name', 'last_name', 'phone', 'normalized_phone')
