import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView
from urllib.parse import urlencode

from bot_conversa.repositories import BotConversaFlowDispatchRepository
from bot_conversa.services import BotConversaDispatchService
from gmail_integration.repositories import GmailDispatchRepository
from gmail_integration.services import GmailDispatchService

from dispatch_flow.services import (
    DispatchFlowAccessService,
    DispatchFlowActionService,
    DispatchFlowAudienceService,
    DispatchFlowWorkspaceService,
)

logger = logging.getLogger('dispatch_flow.debug')


class DispatchFlowAccessMixin(LoginRequiredMixin):
    missing_organization_redirect_url = 'dashboard:home'
    missing_installation_redirect_url = 'integrations:apps'

    def prepare_request_context(self, request):
        active_organization = getattr(request, 'active_organization', None)
        active_membership = getattr(request, 'active_membership', None)

        if active_organization is None:
            messages.info(request, 'Escolha ou crie uma organizacao antes de acessar o fluxo de disparo.')
            return redirect(self.missing_organization_redirect_url)

        if active_membership is None:
            messages.error(request, 'Voce nao tem mais acesso a organizacao ativa.')
            return redirect(self.missing_organization_redirect_url)

        if not DispatchFlowAccessService.has_access(organization=active_organization):
            messages.error(
                request,
                'Instale o Bot Conversa ou o Gmail na organizacao ativa para usar o fluxo de disparo.',
            )
            return redirect(self.missing_installation_redirect_url)

        self.active_organization = active_organization
        self.active_membership = active_membership
        return None

    def dispatch(self, request, *args, **kwargs):
        redirect_response = self.prepare_request_context(request)
        if redirect_response is not None:
            return redirect_response
        return super().dispatch(request, *args, **kwargs)

    def build_base_context(self):
        return {
            'can_manage_dispatch_flow': self.active_membership.can_manage_integrations,
            'can_manage_bot_conversa': self.active_membership.can_manage_integrations,
            'can_manage_gmail': self.active_membership.can_manage_integrations,
        }


class DispatchFlowView(DispatchFlowAccessMixin, TemplateView):
    template_name = 'dispatch_flow/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filter_form = kwargs.get('filter_form') or DispatchFlowWorkspaceService.build_filter_form(self.request.GET or None)
        audience_filter = 'all'
        if filter_form.is_bound and filter_form.is_valid():
            audience_filter = filter_form.cleaned_data.get('audience_filter') or 'all'

        audience_rows = kwargs.get('audience_rows') or DispatchFlowAudienceService.build_rows(
            organization=self.active_organization,
            audience_filter=audience_filter,
        )
        dispatch_form = kwargs.get('dispatch_form') or DispatchFlowWorkspaceService.build_dispatch_form(
            organization=self.active_organization,
            audience_rows=audience_rows,
        )

        context.update(self.build_base_context())
        context.update(
            DispatchFlowWorkspaceService.build_page_state(
                organization=self.active_organization,
                filter_form=filter_form,
                dispatch_form=dispatch_form,
                audience_rows=audience_rows,
            )
        )
        context.update(
            {
                'bot_tag_preflight_modal_open': kwargs.get('bot_tag_preflight_modal_open', False),
                'bot_tag_preflight_people': kwargs.get('bot_tag_preflight_people', []),
                'bot_tag_preflight_modal_errors': kwargs.get('bot_tag_preflight_modal_errors', []),
                'hubspot_preflight_modal_open': kwargs.get('hubspot_preflight_modal_open', False),
                'hubspot_preflight_people': kwargs.get('hubspot_preflight_people', []),
                'hubspot_preflight_modal_errors': kwargs.get('hubspot_preflight_modal_errors', []),
            }
        )
        return context


class DispatchFlowDetailView(DispatchFlowAccessMixin, TemplateView):
    template_name = 'dispatch_flow/detail.html'

    def dispatch(self, request, *args, **kwargs):
        redirect_response = self.prepare_request_context(request)
        if redirect_response is not None:
            return redirect_response

        self.bot_dispatch = None
        self.gmail_dispatch = None

        bot_dispatch_public_id = request.GET.get('bot_dispatch')
        gmail_dispatch_public_id = request.GET.get('gmail_dispatch')

        if not bot_dispatch_public_id and not gmail_dispatch_public_id:
            messages.error(request, 'Nenhum disparo foi informado para acompanhamento.')
            return redirect('dispatch_flow:index')

        if bot_dispatch_public_id:
            self.bot_dispatch = BotConversaFlowDispatchRepository.get_for_organization_and_public_id(
                self.active_organization,
                bot_dispatch_public_id,
            )
            if self.bot_dispatch is None:
                messages.error(request, 'O disparo de WhatsApp informado nao foi encontrado.')
                return redirect('dispatch_flow:index')

        if gmail_dispatch_public_id:
            self.gmail_dispatch = GmailDispatchRepository.get_for_organization_and_public_id(
                self.active_organization,
                gmail_dispatch_public_id,
            )
            if self.gmail_dispatch is None:
                messages.error(request, 'O disparo de Gmail informado nao foi encontrado.')
                return redirect('dispatch_flow:index')

        return super(DispatchFlowAccessMixin, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.build_base_context())
        context.update(
            {
                'bot_dispatch_payload': (
                    BotConversaDispatchService.build_dispatch_payload(dispatch=self.bot_dispatch)
                    if self.bot_dispatch is not None
                    else None
                ),
                'gmail_dispatch_payload': (
                    GmailDispatchService.build_dispatch_payload(dispatch=self.gmail_dispatch)
                    if self.gmail_dispatch is not None
                    else None
                ),
            }
        )
        return context


class DispatchFlowCreateView(DispatchFlowAccessMixin, View):
    HUBSPOT_MODAL_FIELD_NAMES = {
        'hubspot_create_deal_now',
        'hubspot_deal_target_type',
        'hubspot_target_company_public_id',
        'hubspot_target_person_public_id',
        'hubspot_deal_person_public_ids',
        'hubspot_pipeline_public_id',
        'hubspot_stage_id',
    }

    def render_workspace(
        self,
        *,
        request,
        filter_form,
        dispatch_form,
        audience_rows,
        bot_tag_preflight_modal_open=False,
        bot_tag_preflight_people=None,
        bot_tag_preflight_modal_errors=None,
        hubspot_preflight_modal_open=False,
        hubspot_preflight_people=None,
        hubspot_preflight_modal_errors=None,
    ):
        view = DispatchFlowView()
        view.request = request
        view.active_organization = self.active_organization
        view.active_membership = self.active_membership
        return view.render_to_response(
            view.get_context_data(
                filter_form=filter_form,
                dispatch_form=dispatch_form,
                audience_rows=audience_rows,
                bot_tag_preflight_modal_open=bot_tag_preflight_modal_open,
                bot_tag_preflight_people=bot_tag_preflight_people or [],
                bot_tag_preflight_modal_errors=bot_tag_preflight_modal_errors or [],
                hubspot_preflight_modal_open=hubspot_preflight_modal_open,
                hubspot_preflight_people=hubspot_preflight_people or [],
                hubspot_preflight_modal_errors=hubspot_preflight_modal_errors or [],
            )
        )

    def should_open_hubspot_modal(self, *, dispatch_form, post_data):
        if post_data.get('hubspot_preflight_modal_submit'):
            return True
        return any(field_name in dispatch_form.errors for field_name in self.HUBSPOT_MODAL_FIELD_NAMES)

    def post(self, request, *args, **kwargs):
        post_data = request.POST.copy()
        preflight_modal_submit = post_data.get('bot_conversa_tag_modal_submit')
        if preflight_modal_submit in {'skip', 'apply'}:
            post_data['skip_bot_conversa_tag_preflight'] = '1'
            post_data['bot_conversa_tag_preflight_action'] = (
                'apply' if preflight_modal_submit == 'apply' else ''
            )
        hubspot_modal_submit = post_data.get('hubspot_preflight_modal_submit')
        if hubspot_modal_submit in {'skip', 'apply'}:
            post_data['skip_hubspot_preflight'] = '1'
            post_data['hubspot_preflight_action'] = hubspot_modal_submit

        logger.info(
            'dispatch_flow_create:start user_id=%s org_id=%s post_keys=%s',
            getattr(request.user, 'id', None),
            getattr(self.active_organization, 'id', None),
            sorted(post_data.keys()),
        )
        filter_form = DispatchFlowWorkspaceService.build_filter_form(
            {
                'load': '1',
                'audience_filter': post_data.get('audience_filter', 'all'),
            }
        )
        audience_filter = 'all'
        if filter_form.is_valid():
            audience_filter = filter_form.cleaned_data.get('audience_filter') or 'all'
        audience_rows = DispatchFlowAudienceService.build_rows(
            organization=self.active_organization,
            audience_filter=audience_filter,
        )

        dispatch_form = DispatchFlowWorkspaceService.build_dispatch_form(
            organization=self.active_organization,
            audience_rows=audience_rows,
            data=post_data,
        )
        if not dispatch_form.is_valid():
            logger.info(
                'dispatch_flow_create:invalid_form errors=%s',
                dispatch_form.errors.get_json_data(),
            )
            selected_people = DispatchFlowActionService.resolve_people(
                organization=self.active_organization,
                person_public_ids=DispatchFlowWorkspaceService._get_values(post_data, 'person_public_ids'),
            )
            return self.render_workspace(
                request=request,
                filter_form=filter_form,
                dispatch_form=dispatch_form,
                audience_rows=audience_rows,
                hubspot_preflight_modal_open=self.should_open_hubspot_modal(
                    dispatch_form=dispatch_form,
                    post_data=post_data,
                ),
                hubspot_preflight_people=selected_people,
            )

        persons = DispatchFlowActionService.resolve_people(
            organization=self.active_organization,
            person_public_ids=dispatch_form.cleaned_data['person_public_ids'],
        )
        logger.info(
            'dispatch_flow_create:resolved_people count=%s send_bot=%s send_gmail=%s skip_preflight=%s preflight_action=%s selected_tags=%s',
            len(persons),
            dispatch_form.cleaned_data['send_bot_conversa'],
            dispatch_form.cleaned_data['send_gmail'],
            dispatch_form.cleaned_data['skip_bot_conversa_tag_preflight'],
            dispatch_form.cleaned_data['bot_conversa_tag_preflight_action'],
            dispatch_form.cleaned_data['bot_conversa_tag_public_ids'],
        )

        if dispatch_form.cleaned_data['send_bot_conversa'] and not dispatch_form.cleaned_data['skip_bot_conversa_tag_preflight']:
            preflight = DispatchFlowActionService.build_bot_conversa_tag_preflight(
                organization=self.active_organization,
                persons=persons,
            )
            logger.info(
                'dispatch_flow_create:preflight should_prompt=%s untagged_count=%s',
                preflight['should_prompt'],
                len(preflight['untagged_people']),
            )
            if preflight['should_prompt']:
                logger.info('dispatch_flow_create:returning_preflight_modal')
                return self.render_workspace(
                    request=request,
                    filter_form=filter_form,
                    dispatch_form=dispatch_form,
                    audience_rows=audience_rows,
                    bot_tag_preflight_modal_open=True,
                    bot_tag_preflight_people=preflight['untagged_people'],
                )

        if (
            dispatch_form.cleaned_data['send_bot_conversa']
            and dispatch_form.cleaned_data['bot_conversa_tag_preflight_action'] == 'apply'
            and not dispatch_form.cleaned_data['bot_conversa_tag_public_ids']
        ):
            logger.info('dispatch_flow_create:apply_requested_without_tags')
            dispatch_form.add_error('bot_conversa_tag_public_ids', 'Selecione pelo menos uma etiqueta para continuar.')
            return self.render_workspace(
                request=request,
                filter_form=filter_form,
                dispatch_form=dispatch_form,
                audience_rows=audience_rows,
                bot_tag_preflight_modal_open=True,
                bot_tag_preflight_people=DispatchFlowActionService.build_bot_conversa_tag_preflight(
                    organization=self.active_organization,
                    persons=persons,
                )['untagged_people'],
            )

        try:
            logger.info('dispatch_flow_create:applying_tags_if_requested')
            DispatchFlowActionService.apply_bot_conversa_tags_if_requested(
                user=request.user,
                organization=self.active_organization,
                persons=persons,
                tag_public_ids=dispatch_form.cleaned_data['bot_conversa_tag_public_ids'],
                preflight_action=dispatch_form.cleaned_data['bot_conversa_tag_preflight_action'],
            )
        except DispatchFlowActionService.handled_exceptions() as exc:
            logger.exception(
                'dispatch_flow_create:handled_exception skip_preflight=%s preflight_action=%s selected_tags=%s',
                dispatch_form.cleaned_data.get('skip_bot_conversa_tag_preflight'),
                dispatch_form.cleaned_data.get('bot_conversa_tag_preflight_action'),
                dispatch_form.cleaned_data.get('bot_conversa_tag_public_ids'),
            )
            error_messages = []
            if hasattr(exc, 'messages') and exc.messages:
                for message in exc.messages:
                    error_messages.append(message)
                    messages.error(request, message)
            else:
                fallback_message = str(exc)
                error_messages.append(fallback_message)
                messages.error(request, fallback_message)

            return self.render_workspace(
                request=request,
                filter_form=filter_form,
                dispatch_form=dispatch_form,
                audience_rows=audience_rows,
                bot_tag_preflight_modal_open=bool(dispatch_form.cleaned_data.get('send_bot_conversa')),
                bot_tag_preflight_people=DispatchFlowActionService.build_bot_conversa_tag_preflight(
                    organization=self.active_organization,
                    persons=persons,
                )['untagged_people'],
                bot_tag_preflight_modal_errors=error_messages,
            )

        if (
            DispatchFlowAccessService.is_app_installed(
                organization=self.active_organization,
                app_code=DispatchFlowAccessService.HUBSPOT_CODE,
            )
            and not dispatch_form.cleaned_data['skip_hubspot_preflight']
        ):
            hubspot_preflight = DispatchFlowActionService.build_hubspot_preflight(
                organization=self.active_organization,
                persons=persons,
            )
            if hubspot_preflight['should_prompt']:
                logger.info('dispatch_flow_create:returning_hubspot_preflight_modal')
                return self.render_workspace(
                    request=request,
                    filter_form=filter_form,
                    dispatch_form=dispatch_form,
                    audience_rows=audience_rows,
                    hubspot_preflight_modal_open=True,
                    hubspot_preflight_people=hubspot_preflight['selected_people'],
                )

        hubspot_result = {
            'synced_companies': [],
            'synced_people': [],
            'hubspot_deal': None,
        }
        try:
            logger.info('dispatch_flow_create:applying_hubspot_actions_if_requested')
            hubspot_result = DispatchFlowActionService.apply_hubspot_actions_if_requested(
                user=request.user,
                organization=self.active_organization,
                persons=persons,
                preflight_action=dispatch_form.cleaned_data['hubspot_preflight_action'],
                create_deal_now=dispatch_form.cleaned_data['hubspot_create_deal_now'],
                target_type=dispatch_form.cleaned_data['hubspot_deal_target_type'],
                target_company_public_id=dispatch_form.cleaned_data['hubspot_target_company_public_id'],
                target_person_public_id=dispatch_form.cleaned_data['hubspot_target_person_public_id'],
                deal_person_public_ids=dispatch_form.cleaned_data['hubspot_deal_person_public_ids'],
                pipeline_public_id=dispatch_form.cleaned_data['hubspot_pipeline_public_id'],
                stage_id=dispatch_form.cleaned_data['hubspot_stage_id'],
            )
        except DispatchFlowActionService.handled_exceptions() as exc:
            logger.exception(
                'dispatch_flow_create:hubspot_preflight_exception action=%s create_deal=%s',
                dispatch_form.cleaned_data.get('hubspot_preflight_action'),
                dispatch_form.cleaned_data.get('hubspot_create_deal_now'),
            )
            error_messages = []
            if hasattr(exc, 'message_dict'):
                for field_name, field_messages in exc.message_dict.items():
                    for message in field_messages:
                        dispatch_form.add_error(field_name if field_name in dispatch_form.fields else None, message)
                        error_messages.append(message)
            elif hasattr(exc, 'messages') and exc.messages:
                for message in exc.messages:
                    error_messages.append(message)
                    messages.error(request, message)
            else:
                fallback_message = str(exc)
                error_messages.append(fallback_message)
                messages.error(request, fallback_message)

            return self.render_workspace(
                request=request,
                filter_form=filter_form,
                dispatch_form=dispatch_form,
                audience_rows=audience_rows,
                hubspot_preflight_modal_open=True,
                hubspot_preflight_people=persons,
                hubspot_preflight_modal_errors=error_messages,
            )

        try:
            logger.info('dispatch_flow_create:creating_multichannel_dispatch')
            result = DispatchFlowActionService.create_multichannel_dispatch(
                user=request.user,
                organization=self.active_organization,
                person_public_ids=dispatch_form.cleaned_data['person_public_ids'],
                send_bot_conversa=dispatch_form.cleaned_data['send_bot_conversa'],
                flow_public_id=dispatch_form.cleaned_data['flow_public_id'],
                bot_min_delay_seconds=dispatch_form.cleaned_data['bot_min_delay_seconds'],
                bot_max_delay_seconds=dispatch_form.cleaned_data['bot_max_delay_seconds'],
                send_gmail=dispatch_form.cleaned_data['send_gmail'],
                gmail_template_public_id=dispatch_form.cleaned_data['gmail_template_public_id'],
                gmail_cc_emails=dispatch_form.cleaned_data['gmail_cc_emails'],
                gmail_min_delay_seconds=dispatch_form.cleaned_data['gmail_min_delay_seconds'],
                gmail_max_delay_seconds=dispatch_form.cleaned_data['gmail_max_delay_seconds'],
            )
            logger.info(
                'dispatch_flow_create:success bot_dispatch=%s gmail_dispatch=%s',
                getattr(result.get('bot_dispatch'), 'public_id', None),
                getattr(result.get('gmail_dispatch'), 'public_id', None),
            )
        except DispatchFlowActionService.handled_exceptions() as exc:
            logger.exception('dispatch_flow_create:dispatch_exception')
            error_messages = []
            if hasattr(exc, 'messages') and exc.messages:
                for message in exc.messages:
                    error_messages.append(message)
                    messages.error(request, message)
            else:
                fallback_message = str(exc)
                error_messages.append(fallback_message)
                messages.error(request, fallback_message)

            return self.render_workspace(
                request=request,
                filter_form=filter_form,
                dispatch_form=dispatch_form,
                audience_rows=audience_rows,
            )

        if hubspot_result['hubspot_deal'] is not None:
            messages.success(request, f"Negocio '{hubspot_result['hubspot_deal'].name}' criado no HubSpot antes do disparo.")
        elif hubspot_result['synced_companies'] or hubspot_result['synced_people']:
            messages.success(request, 'Dados selecionados foram sincronizados com o HubSpot antes do disparo.')
        if result['bot_dispatch'] and result['gmail_dispatch']:
            messages.success(request, 'Disparos de WhatsApp e Gmail foram criados com sucesso.')
        elif result['bot_dispatch']:
            messages.success(request, 'Disparo de WhatsApp criado com sucesso.')
        elif result['gmail_dispatch']:
            messages.success(request, 'Disparo de Gmail criado com sucesso.')

        query = {}
        if result['bot_dispatch']:
            query['bot_dispatch'] = str(result['bot_dispatch'].public_id)
        if result['gmail_dispatch']:
            query['gmail_dispatch'] = str(result['gmail_dispatch'].public_id)

        detail_url = reverse('dispatch_flow:dispatch_detail')
        if query:
            detail_url = f'{detail_url}?{urlencode(query)}'
        return redirect(detail_url)
