from apollo_integration.models import (
    ApolloCompanySyncLog,
    ApolloPeopleEnrichmentItem,
    ApolloPeopleEnrichmentJob,
    ApolloUsageSnapshot,
)


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


class ApolloPeopleEnrichmentJobRepository:
    @staticmethod
    def list_recent_for_organization(organization, *, limit=10):
        return (
            ApolloPeopleEnrichmentJob.objects.for_organization(organization)
            .with_related_objects()
            .order_by('-started_at', '-created_at')[:limit]
        )

    @staticmethod
    def get_for_public_id(public_id):
        return (
            ApolloPeopleEnrichmentJob.objects.with_related_objects()
            .filter(public_id=public_id)
            .first()
        )

    @staticmethod
    def create(**kwargs):
        return ApolloPeopleEnrichmentJob.objects.create(**kwargs)


class ApolloPeopleEnrichmentItemRepository:
    @staticmethod
    def list_for_job(job):
        return (
            ApolloPeopleEnrichmentItem.objects.with_related_objects()
            .filter(job=job, organization=job.organization)
            .order_by('created_at')
        )

    @staticmethod
    def get_for_job_and_apollo_person_id(job, apollo_person_id):
        return (
            ApolloPeopleEnrichmentItem.objects.with_related_objects()
            .filter(job=job, organization=job.organization, apollo_person_id=apollo_person_id)
            .first()
        )

    @staticmethod
    def bulk_create(items, **kwargs):
        return ApolloPeopleEnrichmentItem.objects.bulk_create(items, **kwargs)
