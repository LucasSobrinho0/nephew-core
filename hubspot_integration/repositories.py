from django.db.models import Q

from hubspot_integration.models import HubSpotDeal, HubSpotPipelineCache, HubSpotSyncLog


class HubSpotPipelineRepository:
    @staticmethod
    def list_for_organization(organization):
        return (
            HubSpotPipelineCache.objects.for_organization(organization)
            .with_related_objects()
            .order_by('name')
        )

    @staticmethod
    def get_for_organization_and_public_id(organization, public_id):
        return (
            HubSpotPipelineCache.objects.for_organization(organization)
            .with_related_objects()
            .filter(public_id=public_id)
            .first()
        )

    @staticmethod
    def get_for_organization_and_hubspot_pipeline_id(organization, hubspot_pipeline_id):
        return (
            HubSpotPipelineCache.objects.for_organization(organization)
            .with_related_objects()
            .filter(hubspot_pipeline_id=hubspot_pipeline_id)
            .first()
        )

    @staticmethod
    def create(**kwargs):
        return HubSpotPipelineCache.objects.create(**kwargs)


class HubSpotDealRepository:
    @staticmethod
    def list_for_organization(organization):
        return (
            HubSpotDeal.objects.for_organization(organization)
            .with_related_objects()
            .order_by('-created_at')
        )

    @staticmethod
    def list_recent_for_organization(organization, limit=5):
        return HubSpotDealRepository.list_for_organization(organization)[:limit]

    @staticmethod
    def get_for_organization_and_public_id(organization, public_id):
        return (
            HubSpotDeal.objects.for_organization(organization)
            .with_related_objects()
            .filter(public_id=public_id)
            .first()
        )

    @staticmethod
    def search_for_organization(organization, query='', limit=20):
        queryset = (
            HubSpotDeal.objects.for_organization(organization)
            .with_related_objects()
            .order_by('-created_at')
        )
        normalized_query = (query or '').strip()
        if normalized_query:
            queryset = queryset.filter(
                Q(name__icontains=normalized_query)
                | Q(company__name__icontains=normalized_query)
            )
        return queryset[:limit]

    @staticmethod
    def create(**kwargs):
        return HubSpotDeal.objects.create(**kwargs)

    @staticmethod
    def list_for_organization_and_hubspot_deal_ids(organization, hubspot_deal_ids):
        return (
            HubSpotDeal.objects.for_organization(organization)
            .with_related_objects()
            .filter(hubspot_deal_id__in=hubspot_deal_ids)
        )


class HubSpotSyncLogRepository:
    @staticmethod
    def list_recent_for_organization(organization, limit=10):
        return (
            HubSpotSyncLog.objects.for_organization(organization)
            .with_related_objects()
            .order_by('-created_at')[:limit]
        )

    @staticmethod
    def create(**kwargs):
        return HubSpotSyncLog.objects.create(**kwargs)

    @staticmethod
    def bulk_create(sync_logs, **kwargs):
        return HubSpotSyncLog.objects.bulk_create(sync_logs, **kwargs)
