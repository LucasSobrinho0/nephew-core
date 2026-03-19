from django.db.models import Q

from bot_conversa.models import (
    BotConversaContact,
    BotConversaFlowCache,
    BotConversaFlowDispatch,
    BotConversaFlowDispatchItem,
    BotConversaPersonTag,
    BotConversaSyncLog,
    BotConversaTag,
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
    def list_for_organization_and_subscriber_ids(organization, external_subscriber_ids):
        return (
            BotConversaContact.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .filter(external_subscriber_id__in=external_subscriber_ids)
        )

    @staticmethod
    def create(**kwargs):
        return BotConversaContact.objects.create(**kwargs)

    @staticmethod
    def bulk_create(contact_links, **kwargs):
        return BotConversaContact.objects.bulk_create(contact_links, **kwargs)

    @staticmethod
    def bulk_update(contact_links, fields, **kwargs):
        if not contact_links:
            return 0
        return BotConversaContact.objects.bulk_update(contact_links, fields, **kwargs)


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


class BotConversaTagRepository:
    @staticmethod
    def list_for_organization(organization):
        return (
            BotConversaTag.objects.for_organization(organization)
            .with_related_objects()
            .order_by('name')
        )

    @staticmethod
    def get_for_organization_and_public_id(organization, public_id):
        return (
            BotConversaTag.objects.for_organization(organization)
            .with_related_objects()
            .filter(public_id=public_id)
            .first()
        )

    @staticmethod
    def get_for_organization_and_external_id(organization, external_tag_id):
        return (
            BotConversaTag.objects.for_organization(organization)
            .with_related_objects()
            .filter(external_tag_id=external_tag_id)
            .first()
        )

    @staticmethod
    def list_for_organization_and_public_ids(organization, public_ids):
        return (
            BotConversaTag.objects.for_organization(organization)
            .with_related_objects()
            .filter(public_id__in=public_ids)
            .order_by('name')
        )

    @staticmethod
    def create(**kwargs):
        return BotConversaTag.objects.create(**kwargs)

    @staticmethod
    def bulk_create(tags, **kwargs):
        return BotConversaTag.objects.bulk_create(tags, **kwargs)

    @staticmethod
    def bulk_update(tags, fields, **kwargs):
        if not tags:
            return 0
        return BotConversaTag.objects.bulk_update(tags, fields, **kwargs)


class BotConversaPersonTagRepository:
    @staticmethod
    def list_for_organization(organization):
        return (
            BotConversaPersonTag.objects.for_organization(organization)
            .with_related_objects()
            .order_by('tag__name', 'person__first_name', 'person__last_name')
        )

    @staticmethod
    def list_for_organization_and_tag(tag):
        return (
            BotConversaPersonTag.objects.for_organization(tag.organization)
            .with_related_objects()
            .filter(tag=tag)
            .order_by('person__first_name', 'person__last_name')
        )

    @staticmethod
    def list_for_organization_and_person(person):
        return (
            BotConversaPersonTag.objects.for_organization(person.organization)
            .with_related_objects()
            .filter(person=person)
            .order_by('tag__name')
        )

    @staticmethod
    def get_for_organization_and_person_and_tag(organization, person, tag):
        return (
            BotConversaPersonTag.objects.for_organization(organization)
            .with_related_objects()
            .filter(person=person, tag=tag)
            .first()
        )

    @staticmethod
    def list_person_ids_for_organization_and_tag_ids(organization, tag_ids):
        return (
            BotConversaPersonTag.objects.for_organization(organization)
            .filter(tag_id__in=tag_ids)
            .values_list('person_id', flat=True)
            .distinct()
        )

    @staticmethod
    def create(**kwargs):
        return BotConversaPersonTag.objects.create(**kwargs)

    @staticmethod
    def bulk_create(person_tags, **kwargs):
        return BotConversaPersonTag.objects.bulk_create(person_tags, **kwargs)

    @staticmethod
    def bulk_update(person_tags, fields, **kwargs):
        if not person_tags:
            return 0
        return BotConversaPersonTag.objects.bulk_update(person_tags, fields, **kwargs)

    @staticmethod
    def delete_for_organization_and_person_excluding_tag_ids(organization, person, keep_tag_ids):
        queryset = BotConversaPersonTag.objects.for_organization(organization).filter(person=person)
        if keep_tag_ids:
            queryset = queryset.exclude(tag_id__in=keep_tag_ids)
        return queryset.delete()


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

    @staticmethod
    def bulk_create(sync_logs, **kwargs):
        return BotConversaSyncLog.objects.bulk_create(sync_logs, **kwargs)


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

    @staticmethod
    def list_runnable_dispatches(*, limit=20, current_time=None):
        from django.utils import timezone

        current_time = current_time or timezone.now()
        return (
            BotConversaFlowDispatch.objects.with_related_objects()
            .filter(
                status__in=[
                    BotConversaFlowDispatch.Status.PENDING,
                    BotConversaFlowDispatch.Status.RUNNING,
                ]
            )
            .filter(
                Q(next_process_after__isnull=True) | Q(next_process_after__lte=current_time)
            )
            .order_by('next_process_after', 'created_at')[:limit]
        )


class BotConversaFlowDispatchItemRepository:
    @staticmethod
    def list_for_dispatch(dispatch):
        return (
            BotConversaFlowDispatchItem.objects.with_related_objects()
            .filter(dispatch=dispatch, organization=dispatch.organization)
            .order_by('created_at', 'target_name')
        )

    @staticmethod
    def list_pending_for_dispatch(dispatch, *, limit):
        return (
            BotConversaFlowDispatchItem.objects.pending()
            .with_related_objects()
            .filter(dispatch=dispatch, organization=dispatch.organization)
            .order_by('created_at')[:limit]
        )

    @staticmethod
    def list_success_person_ids_for_organization(organization):
        return (
            BotConversaFlowDispatchItem.objects.filter(
                organization=organization,
                status=BotConversaFlowDispatchItem.Status.SUCCESS,
            )
            .exclude(person_id__isnull=True)
            .values_list('person_id', flat=True)
            .distinct()
        )

    @staticmethod
    def create(**kwargs):
        return BotConversaFlowDispatchItem.objects.create(**kwargs)

    @staticmethod
    def claim_for_processing(item, *, attempted_at):
        return BotConversaFlowDispatchItem.objects.filter(
            pk=item.pk,
            dispatch=item.dispatch,
            organization=item.organization,
            status=BotConversaFlowDispatchItem.Status.PENDING,
        ).update(
            status=BotConversaFlowDispatchItem.Status.RUNNING,
            last_attempt_at=attempted_at,
            attempt_count=item.attempt_count + 1,
        )

    @staticmethod
    def requeue_stale_running_for_dispatch(dispatch, *, cutoff_time):
        return BotConversaFlowDispatchItem.objects.filter(
            dispatch=dispatch,
            organization=dispatch.organization,
            status=BotConversaFlowDispatchItem.Status.RUNNING,
            last_attempt_at__lt=cutoff_time,
        ).update(
            status=BotConversaFlowDispatchItem.Status.PENDING,
            updated_at=cutoff_time,
        )

    @staticmethod
    def requeue_all_running_for_dispatch(dispatch):
        return BotConversaFlowDispatchItem.objects.filter(
            dispatch=dispatch,
            organization=dispatch.organization,
            status=BotConversaFlowDispatchItem.Status.RUNNING,
        ).update(
            status=BotConversaFlowDispatchItem.Status.PENDING,
        )
