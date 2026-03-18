from django.contrib import admin

from apollo_integration.models import ApolloCompanySyncLog, ApolloUsageSnapshot

admin.site.register(ApolloUsageSnapshot)
admin.site.register(ApolloCompanySyncLog)
