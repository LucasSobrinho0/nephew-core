from django.urls import path

from imports.views import (
    CompanyImportJobCreateView,
    ImportJobDetailView,
    ImportJobProgressView,
    ImportTemplateDownloadView,
    PersonImportJobCreateView,
)

app_name = 'imports'

urlpatterns = [
    path('imports/templates/<str:entity_type>/', ImportTemplateDownloadView.as_view(), name='download_template'),
    path('imports/people/create/', PersonImportJobCreateView.as_view(), name='create_person_job'),
    path('imports/companies/create/', CompanyImportJobCreateView.as_view(), name='create_company_job'),
    path('imports/<uuid:job_public_id>/', ImportJobDetailView.as_view(), name='job_detail'),
    path('imports/<uuid:job_public_id>/progress/', ImportJobProgressView.as_view(), name='job_progress'),
]
