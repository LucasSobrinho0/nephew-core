from django.urls import path

from gmail_integration.views import (
    GmailCredentialSaveView,
    GmailDashboardView,
    GmailDispatchCreateView,
    GmailDispatchDetailView,
    GmailDispatchesView,
    GmailSettingsView,
    GmailTemplateCreateView,
    GmailTemplateUpdateView,
    GmailTemplatesView,
)

app_name = 'gmail_integration'

urlpatterns = [
    path('apps/gmail/', GmailDashboardView.as_view(), name='dashboard'),
    path('apps/gmail/settings/', GmailSettingsView.as_view(), name='settings'),
    path('apps/gmail/settings/save/', GmailCredentialSaveView.as_view(), name='save_settings'),
    path('apps/gmail/templates/', GmailTemplatesView.as_view(), name='templates'),
    path('apps/gmail/templates/create/', GmailTemplateCreateView.as_view(), name='create_template'),
    path('apps/gmail/templates/<uuid:template_public_id>/edit/', GmailTemplateUpdateView.as_view(), name='edit_template'),
    path('apps/gmail/dispatches/', GmailDispatchesView.as_view(), name='dispatches'),
    path('apps/gmail/dispatches/create/', GmailDispatchCreateView.as_view(), name='create_dispatch'),
    path('apps/gmail/dispatches/<uuid:dispatch_public_id>/', GmailDispatchDetailView.as_view(), name='dispatch_detail'),
]
