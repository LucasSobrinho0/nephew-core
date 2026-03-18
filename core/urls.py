from django.contrib import admin
from django.urls import include, path

from common.views import RootRedirectView

urlpatterns = [
    path('', RootRedirectView.as_view(), name='root'),
    path('admin/', admin.site.urls),
    path('', include('accounts.urls')),
    path('', include('organizations.urls')),
    path('', include('dashboard.urls')),
    path('', include('integrations.urls')),
    path('', include('people.urls')),
    path('', include('apollo_integration.urls')),
    path('', include('bot_conversa.urls')),
    path('', include('gmail_integration.urls')),
    path('', include('hubspot_integration.urls')),
]
