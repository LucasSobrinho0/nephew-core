from django.contrib import admin

from apollo_integration.models import (
    ApolloCompanySyncLog,
    ApolloPeopleEnrichmentItem,
    ApolloPeopleEnrichmentJob,
    ApolloUsageSnapshot,
)

admin.site.register(ApolloUsageSnapshot)
admin.site.register(ApolloCompanySyncLog)
admin.site.register(ApolloPeopleEnrichmentJob)
admin.site.register(ApolloPeopleEnrichmentItem)
