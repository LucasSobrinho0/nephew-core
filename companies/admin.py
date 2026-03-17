from django.contrib import admin

from companies.models import Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'hubspot_company_id', 'website', 'phone', 'is_active')
    search_fields = ('name', 'hubspot_company_id', 'website', 'phone')
    list_filter = ('organization', 'is_active')
