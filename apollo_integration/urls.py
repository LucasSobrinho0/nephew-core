from django.urls import path

from apollo_integration.views import (
    ApolloBulkCompanyHubSpotSyncView,
    ApolloBulkRemoteCompanyImportView,
    ApolloBulkRemotePersonImportView,
    ApolloCompaniesView,
    ApolloDashboardView,
    ApolloPeopleView,
)

app_name = 'apollo_integration'

urlpatterns = [
    path('apps/apollo/', ApolloDashboardView.as_view(), name='dashboard'),
    path('apps/apollo/companies/', ApolloCompaniesView.as_view(), name='companies'),
    path('apps/apollo/companies/import/bulk/', ApolloBulkRemoteCompanyImportView.as_view(), name='import_companies_bulk'),
    path('apps/apollo/companies/hubspot/sync/bulk/', ApolloBulkCompanyHubSpotSyncView.as_view(), name='sync_companies_hubspot_bulk'),
    path('apps/apollo/people/', ApolloPeopleView.as_view(), name='people'),
    path('apps/apollo/people/import/bulk/', ApolloBulkRemotePersonImportView.as_view(), name='import_people_bulk'),
]
