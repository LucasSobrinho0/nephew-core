from bot_conversa.models import (
    BotConversaContact,
    BotConversaFlowCache,
    BotConversaFlowDispatch,
    BotConversaFlowDispatchItem,
    BotConversaSyncLog,
)


class BotConversaContactRepository:
    @staticmethod
    def list_for_organization(organization):
        return (
            BotConversaContact.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .order_by('person__first_name', 'person__last_name')
        )

    @staticmethod
    def get_for_organization_and_person(organization, person):
        return (
            BotConversaContact.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .filter(person=person)
            .first()
        )

    @staticmethod
    def get_for_organization_and_subscriber_id(organization, external_subscriber_id):
        return (
            BotConversaContact.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .filter(external_subscriber_id=external_subscriber_id)
            .first()
        )

    @staticmethod
    def get_for_organization_and_phone(organization, normalized_phone):
        return (
            BotConversaContact.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .filter(normalized_phone=normalized_phone)
            .first()
        )

    @staticmethod
    def create(**kwargs):
        return BotConversaContact.objects.create(**kwargs)


class BotConversaFlowCacheRepository:
    @staticmethod
    def list_for_organization(organization):
        return (
            BotConversaFlowCache.objects.for_organization(organization)
            .with_related_objects()
            .order_by('name')
        )

    @staticmethod
    def list_selectable_for_organization(organization):
        return (
            BotConversaFlowCache.objects.for_organization(organization)
            .selectable()
            .with_related_objects()
            .order_by('name')
        )

    @staticmethod
    def get_for_organization_and_public_id(organization, public_id):
        return (
            BotConversaFlowCache.objects.for_organization(organization)
            .with_related_objects()
            .filter(public_id=public_id)
            .first()
        )

    @staticmethod
    def get_for_organization_and_external_id(organization, external_flow_id):
        return (
            BotConversaFlowCache.objects.for_organization(organization)
            .with_related_objects()
            .filter(external_flow_id=external_flow_id)
            .first()
        )

    @staticmethod
    def create(**kwargs):
        return BotConversaFlowCache.objects.create(**kwargs)


class BotConversaSyncLogRepository:
    @staticmethod
    def list_recent_for_organization(organization, *, limit=10):
        return BotConversaSyncLog.objects.filter(organization=organization).select_related(
            'person',
            'contact_link',
            'actor',
        )[:limit]

    @staticmethod
    def create(**kwargs):
        return BotConversaSyncLog.objects.create(**kwargs)


class BotConversaFlowDispatchRepository:
    @staticmethod
    def list_recent_for_organization(organization, *, limit=10):
        return (
            BotConversaFlowDispatch.objects.for_organization(organization)
            .with_related_objects()
            .order_by('-created_at')[:limit]
        )

    @staticmethod
    def get_for_organization_and_public_id(organization, public_id):
        return (
            BotConversaFlowDispatch.objects.for_organization(organization)
            .with_related_objects()
            .filter(public_id=public_id)
            .first()
        )

    @staticmethod
    def create(**kwargs):
        return BotConversaFlowDispatch.objects.create(**kwargs)


class BotConversaFlowDispatchItemRepository:
    @staticmethod
    def list_for_dispatch(dispatch):
        return (
            BotConversaFlowDispatchItem.objects.with_related_objects()
            .filter(dispatch=dispatch)
            .order_by('created_at', 'target_name')
        )

    @staticmethod
    def list_pending_for_dispatch(dispatch, *, limit):
        return (
            BotConversaFlowDispatchItem.objects.pending()
            .with_related_objects()
            .filter(dispatch=dispatch)
            .order_by('created_at')[:limit]
        )

    @staticmethod
    def create(**kwargs):
        return BotConversaFlowDispatchItem.objects.create(**kwargs)
