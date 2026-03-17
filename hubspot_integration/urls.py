from django.urls import path

from hubspot_integration.views import (
    HubSpotCompaniesView,
    HubSpotCompanyCreateView,
    HubSpotCompanySyncView,
    HubSpotDashboardView,
    HubSpotDealCreateView,
    HubSpotDealsView,
    HubSpotPeopleView,
    HubSpotPersonSyncView,
    HubSpotPipelineRefreshView,
    HubSpotPipelinesView,
    HubSpotRemoteCompanyImportView,
    HubSpotRemoteContactImportView,
)

app_name = 'hubspot_integration'

urlpatterns = [
    path('apps/hubspot/', HubSpotDashboardView.as_view(), name='dashboard'),
    path('apps/hubspot/companies/', HubSpotCompaniesView.as_view(), name='companies'),
    path('apps/hubspot/companies/create/', HubSpotCompanyCreateView.as_view(), name='create_company'),
    path('apps/hubspot/companies/sync/', HubSpotCompanySyncView.as_view(), name='sync_company'),
    path('apps/hubspot/companies/import/', HubSpotRemoteCompanyImportView.as_view(), name='import_company'),
    path('apps/hubspot/people/', HubSpotPeopleView.as_view(), name='people'),
    path('apps/hubspot/people/sync/', HubSpotPersonSyncView.as_view(), name='sync_person'),
    path('apps/hubspot/people/import/', HubSpotRemoteContactImportView.as_view(), name='import_person'),
    path('apps/hubspot/pipelines/', HubSpotPipelinesView.as_view(), name='pipelines'),
    path('apps/hubspot/pipelines/refresh/', HubSpotPipelineRefreshView.as_view(), name='refresh_pipelines'),
    path('apps/hubspot/deals/', HubSpotDealsView.as_view(), name='deals'),
    path('apps/hubspot/deals/create/', HubSpotDealCreateView.as_view(), name='create_deal'),
]
