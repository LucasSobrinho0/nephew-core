from django.contrib import admin

from companies.models import Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'apollo_company_id', 'hubspot_company_id', 'website', 'email', 'phone', 'is_active')
    search_fields = ('name', 'apollo_company_id', 'hubspot_company_id', 'website', 'email', 'phone')
    list_filter = ('organization', 'is_active')
