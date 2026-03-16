from django.db.models import Prefetch

from integrations.constants import API_KEY_CREDENTIAL_TYPE
from integrations.models import AppCatalog, AppCredentialAccessAudit, OrganizationAppCredential, OrganizationAppInstallation


class AppCatalogRepository:
    @staticmethod
    def list_active():
        return AppCatalog.objects.active().ordered()

    @staticmethod
    def get_active_by_public_id(public_id):
        return AppCatalog.objects.active().filter(public_id=public_id).first()

    @staticmethod
    def get_by_code(code):
        return AppCatalog.objects.filter(code=code).first()


class AppInstallationRepository:
    @staticmethod
    def list_active_for_organization(organization):
        return (
            OrganizationAppInstallation.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .order_by('app__sort_order', 'app__name')
        )

    @staticmethod
    def list_for_organization(organization):
        current_credentials = Prefetch(
            'credentials',
            queryset=OrganizationAppCredential.objects.current().filter(
                credential_type=API_KEY_CREDENTIAL_TYPE
            ),
            to_attr='current_api_key_credentials',
        )
        return (
            OrganizationAppInstallation.objects.for_organization(organization)
            .with_related_objects()
            .prefetch_related(current_credentials)
            .order_by('app__sort_order', 'app__name')
        )

    @staticmethod
    def get_for_organization_and_app(organization, app):
        return (
            OrganizationAppInstallation.objects.with_related_objects()
            .filter(organization=organization, app=app)
            .first()
        )

    @staticmethod
    def get_for_organization_and_public_id(organization, public_id):
        return (
            OrganizationAppInstallation.objects.with_related_objects()
            .filter(organization=organization, public_id=public_id)
            .first()
        )

    @staticmethod
    def create(**kwargs):
        return OrganizationAppInstallation.objects.create(**kwargs)


class AppCredentialRepository:
    @staticmethod
    def get_current_api_key(installation):
        return (
            OrganizationAppCredential.objects.current()
            .filter(
                installation=installation,
                credential_type=API_KEY_CREDENTIAL_TYPE,
            )
            .first()
        )

    @staticmethod
    def get_latest_version(installation):
        latest_credential = (
            OrganizationAppCredential.objects.for_installation(installation)
            .filter(credential_type=API_KEY_CREDENTIAL_TYPE)
            .order_by('-version')
            .first()
        )
        return latest_credential.version if latest_credential else 0

    @staticmethod
    def create(**kwargs):
        return OrganizationAppCredential.objects.create(**kwargs)

    @staticmethod
    def deactivate_active_credentials(*, installation, updated_by, revoked=False, revoked_at=None):
        current_credentials = OrganizationAppCredential.objects.current().filter(
            installation=installation,
            credential_type=API_KEY_CREDENTIAL_TYPE,
        )

        for credential in current_credentials:
            credential.status = (
                OrganizationAppCredential.Status.REVOKED
                if revoked
                else OrganizationAppCredential.Status.INACTIVE
            )
            credential.updated_by = updated_by
            if revoked:
                credential.revoked_by = updated_by
                credential.revoked_at = revoked_at
            credential.save(update_fields=['status', 'updated_by', 'revoked_by', 'revoked_at', 'updated_at'])


class AppCredentialAccessAuditRepository:
    @staticmethod
    def create(**kwargs):
        return AppCredentialAccessAudit.objects.create(**kwargs)
