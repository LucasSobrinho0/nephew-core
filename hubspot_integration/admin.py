from django.contrib import admin

from hubspot_integration.models import HubSpotDeal, HubSpotPipelineCache, HubSpotSyncLog

admin.site.register(HubSpotPipelineCache)
admin.site.register(HubSpotDeal)
admin.site.register(HubSpotSyncLog)
