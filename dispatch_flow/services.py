from django.core.exceptions import PermissionDenied, ValidationError

from bot_conversa.exceptions import BotConversaApiError, BotConversaConfigurationError
from bot_conversa.repositories import (
    BotConversaFlowCacheRepository,
    BotConversaFlowDispatchItemRepository,
    BotConversaFlowDispatchRepository,
)
from bot_conversa.services import BotConversaDispatchService, BotConversaDispatchWorkspaceService
from dispatch_flow.forms import DispatchFlowCreateForm, DispatchFlowFilterForm
from gmail_integration.exceptions import GmailApiError, GmailConfigurationError
from gmail_integration.repositories import (
    GmailDispatchRecipientRepository,
    GmailDispatchRepository,
    GmailTemplateRepository,
)
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
        return {
            'bot_conversa_enabled': DispatchFlowAccessService.is_app_installed(
                organization=organization,
                app_code=DispatchFlowAccessService.BOT_CONVERSA_CODE,
            ),
            'gmail_enabled': DispatchFlowAccessService.is_app_installed(
                organization=organization,
                app_code=DispatchFlowAccessService.GMAIL_CODE,
            ),
        }


class DispatchFlowAudienceService:
    @staticmethod
    def build_rows(*, organization, audience_filter='all'):
        persons = list(PersonRepository.list_for_organization(organization))
        sent_email_person_ids = set(
            GmailDispatchRecipientRepository.list_sent_person_ids_for_organization(organization)
        )
        sent_whatsapp_person_ids = set(
            BotConversaFlowDispatchItemRepository.list_success_person_ids_for_organization(organization)
        )

        rows = []
        for person in persons:
            email_sent = person.id in sent_email_person_ids
            whatsapp_sent = person.id in sent_whatsapp_person_ids

            if audience_filter == 'email_unsent' and email_sent:
                continue
            if audience_filter == 'whatsapp_unsent' and whatsapp_sent:
                continue
            if audience_filter == 'unsent_both' and (email_sent or whatsapp_sent):
                continue

            rows.append(
                {
                    'person': person,
                    'can_send_gmail': bool(person.email),
                    'can_send_bot_conversa': bool(person.phone),
                    'email_sent': email_sent,
                    'whatsapp_sent': whatsapp_sent,
                }
            )

        return rows

    @staticmethod
    def build_person_choices_from_rows(*, audience_rows):
        return [
            (
                str(row['person'].public_id),
                f"{row['person'].full_name} - {row['person'].email or row['person'].phone or 'Sem contato'}",
            )
            for row in audience_rows
        ]


class DispatchFlowWorkspaceService:
    @staticmethod
    def build_filter_form(data=None):
        return DispatchFlowFilterForm(data or None)

    @staticmethod
    def build_dispatch_form(*, organization, audience_rows, data=None):
        channel_state = DispatchFlowAccessService.build_channel_state(organization=organization)
        return DispatchFlowCreateForm(
            data or None,
            person_choices=DispatchFlowAudienceService.build_person_choices_from_rows(
                audience_rows=audience_rows,
            ),
            bot_flow_choices=(
                []
                if not channel_state['bot_conversa_enabled']
                else BotConversaDispatchWorkspaceService.build_flow_choices(
                    organization=organization,
                )
            ),
            gmail_template_choices=(
                []
                if not channel_state['gmail_enabled']
                else GmailDispatchWorkspaceService.build_template_choices(
                    organization=organization,
                )
            ),
            bot_enabled=channel_state['bot_conversa_enabled'],
            gmail_enabled=channel_state['gmail_enabled'],
        )

    @staticmethod
    def build_page_state(*, organization, filter_form=None, dispatch_form=None, audience_rows=None):
        channel_state = DispatchFlowAccessService.build_channel_state(organization=organization)
        filter_form = filter_form or DispatchFlowWorkspaceService.build_filter_form()
        audience_filter = 'all'
        if filter_form.is_bound and filter_form.is_valid():
            audience_filter = filter_form.cleaned_data.get('audience_filter') or 'all'

        audience_rows = audience_rows or DispatchFlowAudienceService.build_rows(
            organization=organization,
            audience_filter=audience_filter,
        )
        dispatch_form = dispatch_form or DispatchFlowWorkspaceService.build_dispatch_form(
            organization=organization,
            audience_rows=audience_rows,
        )

        return {
            **channel_state,
            'filter_form': filter_form,
            'dispatch_form': dispatch_form,
            'audience_rows': audience_rows,
            'bot_recent_dispatches': BotConversaFlowDispatchRepository.list_recent_for_organization(organization),
            'gmail_dispatches': GmailDispatchRepository.list_for_organization(organization),
        }


class DispatchFlowActionService:
    @staticmethod
    def validate_people_for_channels(*, persons, send_bot_conversa=False, send_gmail=False):
        errors = []

        if send_bot_conversa:
            missing_phone = [person.full_name for person in persons if not person.phone]
            if missing_phone:
                errors.append(
                    'As seguintes pessoas nao possuem telefone para WhatsApp: ' + '; '.join(missing_phone)
                )

        if send_gmail:
            missing_email = [person.full_name for person in persons if not person.email]
            if missing_email:
                errors.append(
                    'As seguintes pessoas nao possuem e-mail para Gmail: ' + '; '.join(missing_email)
                )

        if errors:
            raise ValidationError(errors)

    @staticmethod
    def create_multichannel_dispatch(
        *,
        user,
        organization,
        person_public_ids,
        send_bot_conversa=False,
        flow_public_id='',
        bot_min_delay_seconds=0,
        bot_max_delay_seconds=0,
        send_gmail=False,
        gmail_template_public_id='',
        gmail_cc_emails=None,
        gmail_min_delay_seconds=0,
        gmail_max_delay_seconds=0,
    ):
        persons = list(
            PersonRepository.list_for_organization_and_public_ids(
                organization,
                person_public_ids,
            )
        )
        DispatchFlowActionService.validate_people_for_channels(
            persons=persons,
            send_bot_conversa=send_bot_conversa,
            send_gmail=send_gmail,
        )

        result = {
            'bot_dispatch': None,
            'gmail_dispatch': None,
        }

        if send_bot_conversa:
            flow_cache = BotConversaFlowCacheRepository.get_for_organization_and_public_id(
                organization,
                flow_public_id,
            )
            if flow_cache is None:
                raise ValidationError('Selecione um fluxo valido do Bot Conversa.')

            result['bot_dispatch'] = BotConversaDispatchService.create_dispatch(
                user=user,
                organization=organization,
                flow_cache=flow_cache,
                persons=persons,
                tags=[],
                min_delay_seconds=bot_min_delay_seconds,
                max_delay_seconds=bot_max_delay_seconds,
            )

        if send_gmail:
            template = GmailTemplateRepository.get_for_organization_and_public_id(
                organization,
                gmail_template_public_id,
            )
            if template is None:
                raise ValidationError('O template selecionado nao foi encontrado.')

            result['gmail_dispatch'] = GmailDispatchService.create_dispatch(
                user=user,
                organization=organization,
                template=template,
                to_people=persons,
                cc_emails=gmail_cc_emails or [],
                min_delay_seconds=gmail_min_delay_seconds,
                max_delay_seconds=gmail_max_delay_seconds,
            )

        return result

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
