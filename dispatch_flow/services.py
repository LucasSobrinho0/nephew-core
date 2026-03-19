from django.core.exceptions import PermissionDenied, ValidationError

from bot_conversa.exceptions import BotConversaApiError, BotConversaConfigurationError
from bot_conversa.repositories import BotConversaFlowCacheRepository, BotConversaFlowDispatchRepository, BotConversaTagRepository
from bot_conversa.services import (
    BotConversaDispatchService,
    BotConversaDispatchWorkspaceService,
)
from gmail_integration.exceptions import GmailApiError, GmailConfigurationError
from gmail_integration.repositories import GmailDispatchRepository, GmailTemplateRepository
from gmail_integration.services import GmailDispatchService, GmailDispatchWorkspaceService
from integrations.repositories import AppCatalogRepository, AppInstallationRepository
from people.repositories import PersonRepository


class DispatchFlowAccessService:
    BOT_CONVERSA_CODE = 'bot_conversa'
    GMAIL_CODE = 'gmail'

    @staticmethod
    def is_app_installed(*, organization, app_code):
        if organization is None:
            return False
        app = AppCatalogRepository.get_by_code(app_code)
        if app is None:
            return False
        installation = AppInstallationRepository.get_for_organization_and_app(organization, app)
        return bool(installation and installation.is_installed)

    @staticmethod
    def has_access(*, organization):
        return (
            DispatchFlowAccessService.is_app_installed(
                organization=organization,
                app_code=DispatchFlowAccessService.BOT_CONVERSA_CODE,
            )
            or DispatchFlowAccessService.is_app_installed(
                organization=organization,
                app_code=DispatchFlowAccessService.GMAIL_CODE,
            )
        )

    @staticmethod
    def build_channel_state(*, organization):
        bot_conversa_enabled = DispatchFlowAccessService.is_app_installed(
            organization=organization,
            app_code=DispatchFlowAccessService.BOT_CONVERSA_CODE,
        )
        gmail_enabled = DispatchFlowAccessService.is_app_installed(
            organization=organization,
            app_code=DispatchFlowAccessService.GMAIL_CODE,
        )
        return {
            'bot_conversa_enabled': bot_conversa_enabled,
            'gmail_enabled': gmail_enabled,
        }


class DispatchFlowWorkspaceService:
    @staticmethod
    def build_page_state(*, organization, bot_dispatch_form=None, gmail_dispatch_form=None):
        channel_state = DispatchFlowAccessService.build_channel_state(organization=organization)

        state = {
            **channel_state,
            'bot_dispatch_form': bot_dispatch_form,
            'gmail_dispatch_form': gmail_dispatch_form,
        }

        if channel_state['bot_conversa_enabled']:
            state.update(
                {
                    'bot_dispatch_form': bot_dispatch_form
                    or BotConversaDispatchWorkspaceService.build_dispatch_form(
                        organization=organization,
                    ),
                    'bot_recent_dispatches': BotConversaFlowDispatchRepository.list_recent_for_organization(
                        organization,
                    ),
                    'initial_bot_conversa_audience_count': len(
                        BotConversaDispatchWorkspaceService.build_person_choices(
                            organization=organization,
                        )
                    ),
                }
            )

        if channel_state['gmail_enabled']:
            state.update(
                {
                    'gmail_dispatch_form': gmail_dispatch_form
                    or GmailDispatchWorkspaceService.build_dispatch_form(
                        organization=organization,
                    ),
                    'gmail_dispatches': GmailDispatchRepository.list_for_organization(organization),
                    'initial_gmail_audience_count': len(
                        GmailDispatchWorkspaceService.build_person_choices(
                            organization=organization,
                        )
                    ),
                }
            )

        return state


class DispatchFlowActionService:
    @staticmethod
    def create_bot_conversa_dispatch(
        *,
        user,
        organization,
        flow_public_id,
        person_public_ids,
        tag_public_ids,
        min_delay_seconds,
        max_delay_seconds,
    ):
        flow_cache = BotConversaFlowCacheRepository.get_for_organization_and_public_id(
            organization,
            flow_public_id,
        )
        if flow_cache is None:
            raise ValidationError('Selecione um fluxo valido do Bot Conversa.')

        persons = list(
            PersonRepository.list_for_organization_and_public_ids(
                organization,
                person_public_ids,
            )
        )
        tags = list(
            BotConversaTagRepository.list_for_organization_and_public_ids(
                organization,
                tag_public_ids,
            )
        )
        return BotConversaDispatchService.create_dispatch(
            user=user,
            organization=organization,
            flow_cache=flow_cache,
            persons=persons,
            tags=tags,
            min_delay_seconds=min_delay_seconds,
            max_delay_seconds=max_delay_seconds,
        )

    @staticmethod
    def create_gmail_dispatch(
        *,
        user,
        organization,
        template_public_id,
        person_public_ids,
        cc_emails,
        min_delay_seconds,
        max_delay_seconds,
    ):
        template = GmailTemplateRepository.get_for_organization_and_public_id(
            organization,
            template_public_id,
        )
        if template is None:
            raise ValidationError('O template selecionado nao foi encontrado.')

        to_people = list(
            PersonRepository.list_for_organization_and_public_ids(
                organization,
                person_public_ids,
            )
        )
        return GmailDispatchService.create_dispatch(
            user=user,
            organization=organization,
            template=template,
            to_people=to_people,
            cc_emails=cc_emails,
            min_delay_seconds=min_delay_seconds,
            max_delay_seconds=max_delay_seconds,
        )

    @staticmethod
    def handled_exceptions():
        return (
            PermissionDenied,
            ValidationError,
            BotConversaApiError,
            BotConversaConfigurationError,
            GmailApiError,
            GmailConfigurationError,
        )
