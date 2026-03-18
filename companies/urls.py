from django.urls import path

from companies.views import CompanyCreateView, CompanyListView, CompanyUpdateView

app_name = 'companies'

urlpatterns = [
    path('companies/', CompanyListView.as_view(), name='index'),
    path('companies/create/', CompanyCreateView.as_view(), name='create'),
    path('companies/<uuid:company_public_id>/edit/', CompanyUpdateView.as_view(), name='edit'),
]
