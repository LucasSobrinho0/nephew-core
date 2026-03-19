from django.urls import path

from hubspot_integration.views import (
    HubSpotBulkCompanySyncView,
    HubSpotBulkPersonSyncView,
    HubSpotBulkRemoteCompanyImportView,
    HubSpotBulkRemoteContactImportView,
    HubSpotCompaniesView,
    HubSpotCompanyCreateView,
    HubSpotCompanySyncView,
    HubSpotContactCompanySyncView,
    HubSpotDashboardView,
    HubSpotDealCreateView,
    HubSpotDealSearchView,
    HubSpotDealsView,
    HubSpotPeopleView,
    HubSpotPersonAttachDealView,
    HubSpotPersonCreateView,
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
    path('apps/hubspot/companies/sync/bulk/', HubSpotBulkCompanySyncView.as_view(), name='sync_companies_bulk'),
    path('apps/hubspot/companies/import/', HubSpotRemoteCompanyImportView.as_view(), name='import_company'),
    path('apps/hubspot/companies/import/bulk/', HubSpotBulkRemoteCompanyImportView.as_view(), name='import_companies_bulk'),
    path('apps/hubspot/people/', HubSpotPeopleView.as_view(), name='people'),
    path('apps/hubspot/people/create/', HubSpotPersonCreateView.as_view(), name='create_person'),
    path('apps/hubspot/people/attach-deal/', HubSpotPersonAttachDealView.as_view(), name='attach_person_to_deal'),
    path('apps/hubspot/people/sync/', HubSpotPersonSyncView.as_view(), name='sync_person'),
    path('apps/hubspot/people/sync/bulk/', HubSpotBulkPersonSyncView.as_view(), name='sync_people_bulk'),
    path('apps/hubspot/people/import/', HubSpotRemoteContactImportView.as_view(), name='import_person'),
    path('apps/hubspot/people/import/bulk/', HubSpotBulkRemoteContactImportView.as_view(), name='import_people_bulk'),
    path('apps/hubspot/people/sync-companies/', HubSpotContactCompanySyncView.as_view(), name='sync_contact_companies'),
    path('apps/hubspot/pipelines/', HubSpotPipelinesView.as_view(), name='pipelines'),
    path('apps/hubspot/pipelines/refresh/', HubSpotPipelineRefreshView.as_view(), name='refresh_pipelines'),
    path('apps/hubspot/deals/', HubSpotDealsView.as_view(), name='deals'),
    path('apps/hubspot/deals/create/', HubSpotDealCreateView.as_view(), name='create_deal'),
    path('apps/hubspot/deals/search/', HubSpotDealSearchView.as_view(), name='deal_search'),
]
