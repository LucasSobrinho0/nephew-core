from django.urls import path

from integrations.views import ApiKeyManagementView, AppsCatalogView, InstallAppView, RevealApiKeyView, SaveApiKeyView

app_name = 'integrations'

urlpatterns = [
    path('apps/', AppsCatalogView.as_view(), name='apps'),
    path('apps/install/', InstallAppView.as_view(), name='install_app'),
    path('api-keys/', ApiKeyManagementView.as_view(), name='api_keys'),
    path('api-keys/save/', SaveApiKeyView.as_view(), name='save_api_key'),
    path(
        'api-keys/installations/<uuid:installation_public_id>/reveal/',
        RevealApiKeyView.as_view(),
        name='reveal_api_key',
    ),
]
