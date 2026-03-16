from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from django.urls import NoReverseMatch, reverse

from integrations.constants import APP_NAVIGATION_ITEMS, REVEAL_CONFIRMATION_WORD
from integrations.models import AppCredentialAccessAudit, OrganizationAppCredential, OrganizationAppInstallation
from integrations.repositories import (
    AppCatalogRepository,
    AppCredentialAccessAuditRepository,
    AppCredentialRepository,
    AppInstallationRepository,
)
from organizations.repositories import MembershipRepository


class IntegrationAuthorizationService:
    @staticmethod
    def ensure_organization_access(*, user, organization):
        membership = MembershipRepository.get_for_user_and_organization(user, organization)
        if membership is None:
            raise PermissionDenied('Voce nao faz parte da organizacao ativa.')
        return membership

    @staticmethod
    def ensure_manager_access(*, user, organization):
        membership = IntegrationAuthorizationService.ensure_organization_access(
            user=user,
            organization=organization,
        )
        if not membership.can_manage_integrations:
            raise PermissionDenied('Somente proprietarios e administradores podem gerenciar instalacoes de aplicativos e chaves de API.')
        return membership


class AppMaskingService:
    @staticmethod
    def build_masked_value(secret_value):
        normalized_secret = secret_value.strip()
        last_four = normalized_secret[-4:] if len(normalized_secret) >= 4 else normalized_secret

        prefix = normalized_secret[:4]
        if '_' in normalized_secret[:12]:
            prefix = normalized_secret.rsplit('_', 1)[0]
        elif '-' in normalized_secret[:12]:
            prefix = normalized_secret.rsplit('-', 1)[0]

        prefix = prefix.strip() or 'configured'
        return f'{prefix} ********{last_four}', last_four


class IntegrationCatalogService:
    @staticmethod
    def build_catalog_state(*, organization):
        app_catalog = list(AppCatalogRepository.list_active())
        installations = list(AppInstallationRepository.list_for_organization(organization))

        installation_map = {installation.app_id: installation for installation in installations}

        for installation in installations:
            current_credentials = getattr(installation, 'current_api_key_credentials', [])
            installation.current_api_key_credential = current_credentials[0] if current_credentials else None

        app_cards = []
        for app in app_catalog:
            installation = installation_map.get(app.id)
            current_credential = installation.current_api_key_credential if installation else None
            app_cards.append(
                {
                    'app': app,
                    'installation': installation,
                    'current_api_key_credential': current_credential,
                    'is_installed': bool(installation and installation.status == OrganizationAppInstallation.Status.ACTIVE),
                    'has_api_key': bool(current_credential),
                }
            )

        return app_cards

    @staticmethod
    def build_api_key_state(*, organization):
        installations = list(AppInstallationRepository.list_for_organization(organization))
        app_cards = []

        for installation in installations:
            if installation.status != OrganizationAppInstallation.Status.ACTIVE:
                continue
            if not installation.app.is_active or not installation.app.supports_api_key:
                continue

            current_credentials = getattr(installation, 'current_api_key_credentials', [])
            current_credential = current_credentials[0] if current_credentials else None
            installation.current_api_key_credential = current_credential

            app_cards.append(
                {
                    'app': installation.app,
                    'installation': installation,
                    'current_api_key_credential': current_credential,
                    'is_installed': True,
                    'has_api_key': bool(current_credential),
                }
            )

        return app_cards


class InstalledAppNavigationService:
    @staticmethod
    def build_navigation_items(*, organization):
        if organization is None:
            return []

        navigation_items = []
        installations = AppInstallationRepository.list_active_for_organization(organization)

        for installation in installations:
            navigation_config = APP_NAVIGATION_ITEMS.get(installation.app.code, {})
            route_name = navigation_config.get('route_name', '')

            try:
                route_url = reverse(route_name) if route_name else ''
            except NoReverseMatch:
                route_url = ''

            navigation_items.append(
                {
                    'code': installation.app.code,
                    'label': navigation_config.get('label') or installation.app.name,
                    'icon_class': navigation_config.get('icon_class') or installation.app.icon_class,
                    'url': route_url,
                    'is_available': bool(route_url),
                    'installation_public_id': installation.public_id,
                }
            )

        return navigation_items


class AppInstallationService:
    @staticmethod
    @transaction.atomic
    def install_app(*, user, organization, app):
        IntegrationAuthorizationService.ensure_manager_access(user=user, organization=organization)

        installation = AppInstallationRepository.get_for_organization_and_app(organization, app)
        if installation:
            if installation.status == OrganizationAppInstallation.Status.ACTIVE:
                return installation, False

            installation.status = OrganizationAppInstallation.Status.ACTIVE
            installation.updated_by = user
            installation.save(update_fields=['status', 'updated_by', 'updated_at'])
            return installation, True

        installation = AppInstallationRepository.create(
            organization=organization,
            app=app,
            status=OrganizationAppInstallation.Status.ACTIVE,
            created_by=user,
            updated_by=user,
        )
        return installation, True


class AppCredentialService:
    @staticmethod
    def ensure_installation_access(*, organization, installation):
        if installation.organization_id != organization.id:
            raise PermissionDenied('A instalacao selecionada nao pertence a organizacao ativa.')
        if installation.status != OrganizationAppInstallation.Status.ACTIVE:
            raise ValidationError('Instale o aplicativo antes de configurar a chave de API.')
        if not installation.app.supports_api_key:
            raise ValidationError('Este aplicativo nao suporta credenciais por chave de API.')

    @staticmethod
    @transaction.atomic
    def save_api_key(*, user, organization, installation, api_key):
        IntegrationAuthorizationService.ensure_manager_access(user=user, organization=organization)
        AppCredentialService.ensure_installation_access(organization=organization, installation=installation)

        normalized_secret = api_key.strip()
        if not normalized_secret:
            raise ValidationError('Informe uma chave de API valida.')

        current_credential = AppCredentialRepository.get_current_api_key(installation)
        if current_credential and current_credential.secret_value == normalized_secret:
            return current_credential, False

        AppCredentialRepository.deactivate_active_credentials(
            installation=installation,
            updated_by=user,
        )

        masked_value, last_four = AppMaskingService.build_masked_value(normalized_secret)
        next_version = AppCredentialRepository.get_latest_version(installation) + 1

        credential = AppCredentialRepository.create(
            installation=installation,
            credential_type=OrganizationAppCredential.CredentialType.API_KEY,
            status=OrganizationAppCredential.Status.ACTIVE,
            secret_value=normalized_secret,
            masked_value=masked_value,
            last_four=last_four,
            version=next_version,
            created_by=user,
            updated_by=user,
        )

        installation.updated_by = user
        installation.save(update_fields=['updated_by', 'updated_at'])
        return credential, True

    @staticmethod
    def reveal_api_key(
        *,
        user,
        organization,
        installation,
        confirmation_word,
        ip_address=None,
        user_agent='',
    ):
        IntegrationAuthorizationService.ensure_manager_access(user=user, organization=organization)
        AppCredentialService.ensure_installation_access(organization=organization, installation=installation)

        credential = AppCredentialRepository.get_current_api_key(installation)
        if credential is None:
            AppCredentialService.audit_reveal_attempt(
                organization=organization,
                installation=installation,
                credential=None,
                actor=user,
                outcome=AppCredentialAccessAudit.Outcome.NOT_FOUND,
                reason='missing_active_credential',
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise ValidationError('Nao existe uma chave de API ativa configurada para este aplicativo.')

        if confirmation_word.strip() != REVEAL_CONFIRMATION_WORD:
            AppCredentialService.audit_reveal_attempt(
                organization=organization,
                installation=installation,
                credential=credential,
                actor=user,
                outcome=AppCredentialAccessAudit.Outcome.DENIED,
                reason='invalid_confirmation_word',
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise ValidationError('A palavra de confirmacao esta invalida.')

        AppCredentialService.audit_reveal_attempt(
            organization=organization,
            installation=installation,
            credential=credential,
            actor=user,
            outcome=AppCredentialAccessAudit.Outcome.SUCCESS,
            reason='confirmation_accepted',
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return credential

    @staticmethod
    def audit_reveal_attempt(
        *,
        organization,
        installation,
        credential,
        actor,
        outcome,
        reason,
        ip_address,
        user_agent,
    ):
        AppCredentialAccessAuditRepository.create(
            organization=organization,
            installation=installation,
            credential=credential,
            app=installation.app if installation else None,
            actor=actor,
            event_type=AppCredentialAccessAudit.EventType.REVEAL,
            outcome=outcome,
            reason=reason,
            ip_address=ip_address,
            user_agent=(user_agent or '')[:255],
        )
