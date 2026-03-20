from django.core.exceptions import PermissionDenied, ValidationError

from bot_conversa.exceptions import BotConversaApiError, BotConversaConfigurationError
from bot_conversa.repositories import (
    BotConversaFlowCacheRepository,
    BotConversaFlowDispatchItemRepository,
    BotConversaFlowDispatchRepository,
    BotConversaTagRepository,
)
from bot_conversa.services import (
    BotConversaDispatchService,
    BotConversaDispatchWorkspaceService,
    BotConversaTagPreflightService,
    BotConversaTagService,
)
from dispatch_flow.forms import DispatchFlowCreateForm, DispatchFlowFilterForm
from gmail_integration.exceptions import GmailApiError, GmailConfigurationError
from gmail_integration.repositories import (
    GmailDispatchRecipientRepository,
    GmailDispatchRepository,
    GmailTemplateRepository,
)
from gmail_integration.services import GmailDispatchService, GmailDispatchWorkspaceService
from hubspot_integration.exceptions import HubSpotApiError, HubSpotConfigurationError
from hubspot_integration.repositories import HubSpotPipelineRepository
from hubspot_integration.services import (
    HubSpotCompanyService,
    HubSpotContactService,
    HubSpotDealService,
    HubSpotInstallationService,
    HubSpotPipelineService,
)
from integrations.repositories import AppCatalogRepository, AppInstallationRepository
from companies.repositories import CompanyRepository
from people.repositories import PersonRepository


class DispatchFlowAccessService:
    BOT_CONVERSA_CODE = 'bot_conversa'
    GMAIL_CODE = 'gmail'
    HUBSPOT_CODE = 'hubspot'

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
            'hubspot_enabled': DispatchFlowAccessService.is_app_installed(
                organization=organization,
                app_code=DispatchFlowAccessService.HUBSPOT_CODE,
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
    def _get_values(data, key):
        if data is None:
            return []
        if hasattr(data, 'getlist'):
            return [value for value in data.getlist(key) if str(value).strip()]
        raw_value = data.get(key)
        if raw_value is None:
            return []
        if isinstance(raw_value, (list, tuple)):
            return [value for value in raw_value if str(value).strip()]
        return [raw_value] if str(raw_value).strip() else []

    @staticmethod
    def _set_values(data, key, values):
        if hasattr(data, 'setlist'):
            data.setlist(key, list(values))
            return
        data[key] = list(values)

    @staticmethod
    def build_hubspot_preflight_state(*, organization, selected_people, data=None):
        selected_people = list(selected_people or [])
        all_companies = list(CompanyRepository.list_for_organization(organization))
        all_people = list(PersonRepository.list_for_organization(organization))
        selected_people_by_public_id = {str(person.public_id): person for person in selected_people}
        all_people_by_company_id = {}
        unassigned_people = []
        for person in all_people:
            if person.company_id is None:
                unassigned_people.append(person)
                continue
            all_people_by_company_id.setdefault(person.company_id, []).append(person)
        selected_company_counts = {}
        for person in selected_people:
            if person.company_id:
                selected_company_counts[person.company_id] = selected_company_counts.get(person.company_id, 0) + 1

        ordered_companies = sorted(
            all_companies,
            key=lambda company: (-selected_company_counts.get(company.id, 0), company.name.lower()),
        )
        company_choices = [(str(company.public_id), company.name) for company in ordered_companies]
        person_choices = [
            (
                str(person.public_id),
                f"{person.full_name} - {person.company.name if person.company else 'Sem empresa'}",
            )
            for person in selected_people
        ]

        submitted_target_type = ''
        submitted_company_public_id = ''
        submitted_person_public_id = ''
        submitted_deal_person_public_ids = []
        if data is not None:
            submitted_target_type = str(data.get('hubspot_deal_target_type') or '').strip()
            submitted_company_public_id = str(data.get('hubspot_target_company_public_id') or '').strip()
            submitted_person_public_id = str(data.get('hubspot_target_person_public_id') or '').strip()
            submitted_deal_person_public_ids = [
                str(value).strip()
                for value in DispatchFlowWorkspaceService._get_values(data, 'hubspot_deal_person_public_ids')
            ]

        default_company = None
        if submitted_company_public_id:
            default_company = next(
                (company for company in ordered_companies if str(company.public_id) == submitted_company_public_id),
                None,
            )
        if default_company is None:
            default_company = next(
                (person.company for person in selected_people if person.company_id),
                None,
            )

        default_target_type = submitted_target_type if submitted_target_type in {'company', 'person'} else (
            'company' if default_company is not None else 'person'
        )

        default_person = None
        if submitted_person_public_id:
            default_person = selected_people_by_public_id.get(submitted_person_public_id)
        if default_person is None and selected_people:
            default_person = selected_people[0]

        candidate_people = []
        company_people = []
        allow_manual_company_contacts = False
        company_contact_warning = ''
        if default_company is not None:
            company_people = [
                person
                for person in selected_people
                if person.company_id == default_company.id
            ]
            candidate_people = company_people
        else:
            candidate_people = []

        deal_person_choices = [
            (
                str(person.public_id),
                f"{person.full_name} - {person.company.name if person.company else 'Sem empresa'}",
            )
            for person in candidate_people
        ]

        if submitted_deal_person_public_ids:
            default_deal_person_public_ids = submitted_deal_person_public_ids
        elif default_company is not None:
            default_deal_person_public_ids = [
                str(person.public_id)
                for person in company_people
            ]
        else:
            default_deal_person_public_ids = []

        if selected_people and not any(person.company_id for person in selected_people):
            company_contact_warning = (
                'Nenhuma das pessoas selecionadas no disparo possui empresa vinculada. '
                'No modo empresa, o sistema cria negocios em loop a partir das empresas das pessoas selecionadas.'
            )

        return {
            'company_choices': company_choices,
            'person_choices': person_choices,
            'deal_person_choices': deal_person_choices,
            'pipeline_choices': [
                (str(pipeline.public_id), pipeline.name)
                for pipeline in HubSpotPipelineRepository.list_for_organization(organization)
            ],
            'stage_choices': HubSpotPipelineService.build_stage_choices(organization=organization),
            'default_target_type': default_target_type,
            'default_company_public_id': str(default_company.public_id) if default_company is not None else '',
            'default_person_public_id': str(default_person.public_id) if default_person is not None else '',
            'default_deal_person_public_ids': default_deal_person_public_ids,
            'company_contact_warning': company_contact_warning,
            'allow_manual_company_contacts': allow_manual_company_contacts,
        }

    @staticmethod
    def build_filter_form(data=None):
        return DispatchFlowFilterForm(data or None)

    @staticmethod
    def build_dispatch_form(*, organization, audience_rows, data=None):
        channel_state = DispatchFlowAccessService.build_channel_state(organization=organization)
        normalized_data = data.copy() if data is not None and hasattr(data, 'copy') else data
        selected_people = []
        hubspot_preflight_state = {
            'company_choices': [],
            'person_choices': [],
            'deal_person_choices': [],
            'pipeline_choices': [],
            'stage_choices': [],
            'default_target_type': '',
            'default_company_public_id': '',
            'default_person_public_id': '',
            'default_deal_person_public_ids': [],
            'company_contact_warning': '',
            'allow_manual_company_contacts': False,
        }

        if channel_state['hubspot_enabled'] and normalized_data is not None:
            audience_people_by_public_id = {
                str(row['person'].public_id): row['person']
                for row in audience_rows
            }
            selected_people = [
                audience_people_by_public_id[public_id]
                for public_id in DispatchFlowWorkspaceService._get_values(normalized_data, 'person_public_ids')
                if public_id in audience_people_by_public_id
            ]
            hubspot_preflight_state = DispatchFlowWorkspaceService.build_hubspot_preflight_state(
                organization=organization,
                selected_people=selected_people,
                data=normalized_data,
            )
            if not DispatchFlowWorkspaceService._get_values(normalized_data, 'hubspot_deal_target_type') and hubspot_preflight_state['default_target_type']:
                normalized_data['hubspot_deal_target_type'] = hubspot_preflight_state['default_target_type']
            if not DispatchFlowWorkspaceService._get_values(normalized_data, 'hubspot_target_company_public_id') and hubspot_preflight_state['default_company_public_id']:
                normalized_data['hubspot_target_company_public_id'] = hubspot_preflight_state['default_company_public_id']
            if not DispatchFlowWorkspaceService._get_values(normalized_data, 'hubspot_target_person_public_id') and hubspot_preflight_state['default_person_public_id']:
                normalized_data['hubspot_target_person_public_id'] = hubspot_preflight_state['default_person_public_id']
            if not DispatchFlowWorkspaceService._get_values(normalized_data, 'hubspot_deal_person_public_ids') and hubspot_preflight_state['default_deal_person_public_ids']:
                DispatchFlowWorkspaceService._set_values(
                    normalized_data,
                    'hubspot_deal_person_public_ids',
                    hubspot_preflight_state['default_deal_person_public_ids'],
                )

        return DispatchFlowCreateForm(
            normalized_data or None,
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
            bot_tag_choices=(
                []
                if not channel_state['bot_conversa_enabled']
                else BotConversaTagService.build_tag_choice_rows(
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
            hubspot_enabled=channel_state['hubspot_enabled'],
            hubspot_company_choices=hubspot_preflight_state['company_choices'],
            hubspot_person_choices=hubspot_preflight_state['person_choices'],
            hubspot_deal_person_choices=hubspot_preflight_state['deal_person_choices'],
            hubspot_pipeline_choices=hubspot_preflight_state['pipeline_choices'],
            hubspot_stage_choices=hubspot_preflight_state['stage_choices'],
            hubspot_default_target_type=hubspot_preflight_state['default_target_type'],
            hubspot_default_company_public_id=hubspot_preflight_state['default_company_public_id'],
            hubspot_default_person_public_id=hubspot_preflight_state['default_person_public_id'],
            hubspot_default_deal_person_public_ids=hubspot_preflight_state['default_deal_person_public_ids'],
            hubspot_company_contact_warning=hubspot_preflight_state['company_contact_warning'],
            hubspot_allow_manual_company_contacts=hubspot_preflight_state['allow_manual_company_contacts'],
            form_id='dispatchFlowCreateForm',
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
    def resolve_people(*, organization, person_public_ids):
        return list(
            PersonRepository.list_for_organization_and_public_ids(
                organization,
                person_public_ids,
            )
        )

    @staticmethod
    def build_bot_conversa_tag_preflight(*, organization, persons):
        untagged_people = BotConversaTagPreflightService.list_untagged_people(
            organization=organization,
            persons=persons,
        )
        return {
            'should_prompt': bool(untagged_people),
            'untagged_people': untagged_people,
            'tag_choices': BotConversaTagService.build_tag_choice_rows(organization=organization),
        }

    @staticmethod
    def apply_bot_conversa_tags_if_requested(
        *,
        user,
        organization,
        persons,
        tag_public_ids,
        preflight_action='',
    ):
        if preflight_action == 'apply' and not tag_public_ids:
            raise ValidationError({'bot_conversa_tag_public_ids': ['Selecione pelo menos uma etiqueta para continuar.']})
        if not tag_public_ids:
            return []
        return BotConversaTagPreflightService.apply_tags_by_public_ids(
            user=user,
            organization=organization,
            persons=persons,
            tag_public_ids=tag_public_ids,
        )

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
    def build_hubspot_preflight(*, organization, persons):
        if not DispatchFlowAccessService.is_app_installed(
            organization=organization,
            app_code=DispatchFlowAccessService.HUBSPOT_CODE,
        ):
            return {
                'should_prompt': False,
                'selected_people': [],
            }
        return {
            'should_prompt': bool(persons),
            'selected_people': persons,
        }

    @staticmethod
    def apply_hubspot_actions_if_requested(
        *,
        user,
        organization,
        persons,
        preflight_action='',
        create_deal_now=False,
        target_type='',
        target_company_public_id='',
        target_person_public_id='',
        deal_person_public_ids=None,
        pipeline_public_id='',
        stage_id='',
    ):
        if preflight_action != 'apply':
            return {
                'synced_companies': [],
                'synced_people': [],
                'hubspot_deal': None,
            }

        HubSpotInstallationService.get_installation(organization=organization)

        unique_persons = []
        seen_person_ids = set()
        for person in persons:
            if person.id in seen_person_ids:
                continue
            unique_persons.append(person)
            seen_person_ids.add(person.id)

        unique_companies = []
        seen_company_ids = set()
        for person in unique_persons:
            if person.company_id and person.company_id not in seen_company_ids:
                unique_companies.append(person.company)
                seen_company_ids.add(person.company_id)

        target_company = None
        target_person = None
        pipeline = None

        if create_deal_now:
            pipeline = HubSpotPipelineRepository.get_for_organization_and_public_id(
                organization,
                pipeline_public_id,
            )
            if pipeline is None:
                raise ValidationError('Selecione um pipeline valido do HubSpot.')

            if target_type == 'company':
                company_grouped_people = {}
                for person in unique_persons:
                    if person.company_id is None:
                        continue
                    company_grouped_people.setdefault(person.company_id, []).append(person)
                if not company_grouped_people:
                    raise ValidationError(
                        {
                            'hubspot_deal_target_type': [
                                'Selecione pelo menos uma pessoa com empresa vinculada para criar negocios por empresa.'
                            ]
                        }
                    )
                for company_id in company_grouped_people:
                    if company_id not in seen_company_ids:
                        company = CompanyRepository.get_for_organization_and_public_id(
                            organization,
                            company_grouped_people[company_id][0].company.public_id,
                        )
                        if company is not None:
                            unique_companies.append(company)
                            seen_company_ids.add(company.id)
            elif target_type == 'person':
                target_person = PersonRepository.get_for_organization_and_public_id(
                    organization,
                    target_person_public_id,
                )
                if target_person is None:
                    raise ValidationError({'hubspot_target_person_public_id': ['Selecione uma pessoa valida para o negocio.']})
                if target_person.company is None:
                    raise ValidationError(
                        {
                            'hubspot_target_person_public_id': [
                                'A pessoa escolhida precisa estar vinculada a uma empresa local para criar o negocio.'
                            ]
                        }
                    )
                target_company = target_person.company
                if target_company.id not in seen_company_ids:
                    unique_companies.append(target_company)
                    seen_company_ids.add(target_company.id)
                if target_person.id not in seen_person_ids:
                    unique_persons.append(target_person)
                    seen_person_ids.add(target_person.id)
            else:
                raise ValidationError({'hubspot_deal_target_type': ['Selecione como o negocio sera criado.']})

        companies_to_sync = [
            company for company in unique_companies
            if company is not None and not company.hubspot_company_id
        ]
        synced_companies = []
        if companies_to_sync:
            synced_companies = HubSpotCompanyService.sync_companies(
                user=user,
                organization=organization,
                companies=companies_to_sync,
            )
            synced_company_by_id = {
                company.id: company
                for company in synced_companies
            }
            if target_company is not None and target_company.id in synced_company_by_id:
                target_company = synced_company_by_id[target_company.id]
            elif target_company is not None and not target_company.hubspot_company_id:
                target_company = CompanyRepository.get_for_organization_and_public_id(
                    organization,
                    target_company.public_id,
                )

        persons_to_sync = list(unique_persons)

        missing_people = [
            person for person in persons_to_sync
            if not person.hubspot_contact_id
        ]
        synced_people = []
        if missing_people:
            synced_people = HubSpotContactService.sync_people(
                user=user,
                organization=organization,
                persons=missing_people,
            )
            synced_person_by_id = {
                person.id: person
                for person in synced_people
            }
            if target_person is not None and target_person.id in synced_person_by_id:
                target_person = synced_person_by_id[target_person.id]
            elif target_person is not None and not target_person.hubspot_contact_id:
                target_person = PersonRepository.get_for_organization_and_public_id(
                    organization,
                    target_person.public_id,
                )
        reloaded_people_by_id = {
            person.id: person
            for person in PersonRepository.list_for_organization(organization)
            if person.id in seen_person_ids
        }
        hubspot_deals = []
        if create_deal_now and target_company is not None and pipeline is not None:
            hubspot_deal = HubSpotDealService.create_deal(
                user=user,
                organization=organization,
                company=target_company,
                pipeline=pipeline,
                deal_name=target_person.full_name,
                stage_id=stage_id,
                amount='',
                persons=[target_person],
            )
            hubspot_deals.append(hubspot_deal)
        elif create_deal_now and target_type == 'company' and pipeline is not None:
            companies_for_deals = {}
            for person in unique_persons:
                if person.company_id is None:
                    continue
                companies_for_deals.setdefault(person.company_id, []).append(
                    reloaded_people_by_id.get(person.id, person)
                )
            for company_id, company_people in companies_for_deals.items():
                loop_company = CompanyRepository.get_for_organization_and_public_id(
                    organization,
                    company_people[0].company.public_id,
                )
                if loop_company is None:
                    continue
                hubspot_deals.append(HubSpotDealService.create_deal(
                    user=user,
                    organization=organization,
                    company=loop_company,
                    pipeline=pipeline,
                    deal_name=loop_company.name,
                    stage_id=stage_id,
                    amount='',
                    persons=company_people,
                ))

        return {
            'synced_companies': synced_companies,
            'synced_people': synced_people,
            'hubspot_deal': hubspot_deals[0] if hubspot_deals else None,
            'hubspot_deals': hubspot_deals,
        }

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
        persons = DispatchFlowActionService.resolve_people(
            organization=organization,
            person_public_ids=person_public_ids,
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
            HubSpotApiError,
            HubSpotConfigurationError,
        )
