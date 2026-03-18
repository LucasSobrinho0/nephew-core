from apollo_integration.models import ApolloCompanySyncLog, ApolloUsageSnapshot


class ApolloCompanySyncLogRepository:
    @staticmethod
    def list_recent_for_organization(organization, *, limit=10):
        return (
            ApolloCompanySyncLog.objects.for_organization(organization)
            .with_related_objects()
            .order_by('-created_at')[:limit]
        )

    @staticmethod
    def create(**kwargs):
        return ApolloCompanySyncLog.objects.create(**kwargs)

    @staticmethod
    def bulk_create(sync_logs, **kwargs):
        return ApolloCompanySyncLog.objects.bulk_create(sync_logs, **kwargs)


class ApolloUsageSnapshotRepository:
    @staticmethod
    def get_latest_for_organization(organization):
        return (
            ApolloUsageSnapshot.objects.for_organization(organization)
            .with_related_objects()
            .order_by('-fetched_at', '-created_at')
            .first()
        )

    @staticmethod
    def create(**kwargs):
        return ApolloUsageSnapshot.objects.create(**kwargs)
