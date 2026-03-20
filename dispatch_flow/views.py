from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from dispatch_flow.services import (
    DispatchFlowAccessService,
    DispatchFlowActionService,
    DispatchFlowAudienceService,
    DispatchFlowWorkspaceService,
)


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
            }
        )
        return context


class DispatchFlowCreateView(DispatchFlowAccessMixin, View):
    def post(self, request, *args, **kwargs):
        filter_form = DispatchFlowWorkspaceService.build_filter_form(
            {
                'load': '1',
                'audience_filter': request.POST.get('audience_filter', 'all'),
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
            data=request.POST,
        )
        if not dispatch_form.is_valid():
            view = DispatchFlowView()
            view.request = request
            view.active_organization = self.active_organization
            view.active_membership = self.active_membership
            return view.render_to_response(
                view.get_context_data(
                    filter_form=filter_form,
                    dispatch_form=dispatch_form,
                    audience_rows=audience_rows,
                )
            )

        persons = DispatchFlowActionService.resolve_people(
            organization=self.active_organization,
            person_public_ids=dispatch_form.cleaned_data['person_public_ids'],
        )

        if dispatch_form.cleaned_data['send_bot_conversa'] and not dispatch_form.cleaned_data['skip_bot_conversa_tag_preflight']:
            preflight = DispatchFlowActionService.build_bot_conversa_tag_preflight(
                organization=self.active_organization,
                persons=persons,
            )
            if preflight['should_prompt']:
                view = DispatchFlowView()
                view.request = request
                view.active_organization = self.active_organization
                view.active_membership = self.active_membership
                return view.render_to_response(
                    view.get_context_data(
                        filter_form=filter_form,
                        dispatch_form=dispatch_form,
                        audience_rows=audience_rows,
                        bot_tag_preflight_modal_open=True,
                        bot_tag_preflight_people=preflight['untagged_people'],
                )
                )

        if (
            dispatch_form.cleaned_data['send_bot_conversa']
            and dispatch_form.cleaned_data['bot_conversa_tag_preflight_action'] == 'apply'
            and not dispatch_form.cleaned_data['bot_conversa_tag_public_ids']
        ):
            dispatch_form.add_error('bot_conversa_tag_public_ids', 'Selecione pelo menos uma etiqueta para continuar.')
            view = DispatchFlowView()
            view.request = request
            view.active_organization = self.active_organization
            view.active_membership = self.active_membership
            return view.render_to_response(
                view.get_context_data(
                    filter_form=filter_form,
                    dispatch_form=dispatch_form,
                    audience_rows=audience_rows,
                    bot_tag_preflight_modal_open=True,
                    bot_tag_preflight_people=DispatchFlowActionService.build_bot_conversa_tag_preflight(
                        organization=self.active_organization,
                        persons=persons,
                    )['untagged_people'],
                )
            )

        try:
            DispatchFlowActionService.apply_bot_conversa_tags_if_requested(
                user=request.user,
                organization=self.active_organization,
                persons=persons,
                tag_public_ids=dispatch_form.cleaned_data['bot_conversa_tag_public_ids'],
                preflight_action=dispatch_form.cleaned_data['bot_conversa_tag_preflight_action'],
            )
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
        except DispatchFlowActionService.handled_exceptions() as exc:
            error_messages = []
            if hasattr(exc, 'messages') and exc.messages:
                for message in exc.messages:
                    error_messages.append(message)
                    messages.error(request, message)
            else:
                fallback_message = str(exc)
                error_messages.append(fallback_message)
                messages.error(request, fallback_message)

            view = DispatchFlowView()
            view.request = request
            view.active_organization = self.active_organization
            view.active_membership = self.active_membership
            return view.render_to_response(
                view.get_context_data(
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
            )

        if result['bot_dispatch'] and result['gmail_dispatch']:
            messages.success(request, 'Disparos de WhatsApp e Gmail foram criados com sucesso.')
        elif result['bot_dispatch']:
            messages.success(request, 'Disparo de WhatsApp criado com sucesso.')
        elif result['gmail_dispatch']:
            messages.success(request, 'Disparo de Gmail criado com sucesso.')

        return redirect('dispatch_flow:index')
