from gmail_integration.models import GmailCredential, GmailDispatch, GmailDispatchRecipient, GmailTemplate


class GmailCredentialRepository:
    @staticmethod
    def get_for_organization(organization):
        return (
            GmailCredential.objects.for_organization(organization)
            .with_related_objects()
            .first()
        )

    @staticmethod
    def get_for_installation(installation):
        return (
            GmailCredential.objects.with_related_objects()
            .filter(installation=installation)
            .first()
        )

    @staticmethod
    def create(**kwargs):
        return GmailCredential.objects.create(**kwargs)


class GmailTemplateRepository:
    @staticmethod
    def list_for_organization(organization):
        return (
            GmailTemplate.objects.for_organization(organization)
            .with_related_objects()
            .order_by('name')
        )

    @staticmethod
    def list_active_for_organization(organization):
        return (
            GmailTemplate.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .order_by('name')
        )

    @staticmethod
    def get_for_organization_and_public_id(organization, public_id):
        return (
            GmailTemplate.objects.for_organization(organization)
            .with_related_objects()
            .filter(public_id=public_id)
            .first()
        )

    @staticmethod
    def create(**kwargs):
        return GmailTemplate.objects.create(**kwargs)


class GmailDispatchRepository:
    @staticmethod
    def list_for_organization(organization):
        return (
            GmailDispatch.objects.for_organization(organization)
            .with_related_objects()
            .order_by('-created_at')
        )

    @staticmethod
    def list_recent_for_organization(organization, limit=5):
        return GmailDispatchRepository.list_for_organization(organization)[:limit]

    @staticmethod
    def get_for_organization_and_public_id(organization, public_id):
        return (
            GmailDispatch.objects.for_organization(organization)
            .with_related_objects()
            .filter(public_id=public_id)
            .first()
        )

    @staticmethod
    def create(**kwargs):
        return GmailDispatch.objects.create(**kwargs)


class GmailDispatchRecipientRepository:
    @staticmethod
    def list_for_dispatch(dispatch):
        return (
            GmailDispatchRecipient.objects.with_related_objects()
            .filter(dispatch=dispatch, organization=dispatch.organization)
            .order_by('first_name_snapshot', 'last_name_snapshot', 'email_snapshot')
        )

    @staticmethod
    def list_pending_for_dispatch(dispatch, *, limit):
        return (
            GmailDispatchRecipient.objects.with_related_objects()
            .filter(
                dispatch=dispatch,
                organization=dispatch.organization,
                status=GmailDispatchRecipient.Status.PENDING,
            )
            .order_by('created_at')[:limit]
        )

    @staticmethod
    def list_sent_person_ids_for_organization(organization):
        return (
            GmailDispatchRecipient.objects.filter(
                organization=organization,
                status=GmailDispatchRecipient.Status.SENT,
            )
            .exclude(person_id__isnull=True)
            .values_list('person_id', flat=True)
            .distinct()
        )

    @staticmethod
    def claim_for_processing(recipient):
        return GmailDispatchRecipient.objects.filter(
            pk=recipient.pk,
            dispatch=recipient.dispatch,
            organization=recipient.organization,
            status=GmailDispatchRecipient.Status.PENDING,
        ).update(status=GmailDispatchRecipient.Status.RUNNING)

    @staticmethod
    def create(**kwargs):
        return GmailDispatchRecipient.objects.create(**kwargs)
