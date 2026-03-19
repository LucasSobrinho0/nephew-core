from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from bot_conversa.services import BotConversaDispatchWorkspaceService
from dispatch_flow.services import (
    DispatchFlowAccessService,
    DispatchFlowActionService,
    DispatchFlowWorkspaceService,
)
from gmail_integration.services import GmailDispatchWorkspaceService

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
        context.update(self.build_base_context())
        context.update(
            DispatchFlowWorkspaceService.build_page_state(
                organization=self.active_organization,
                bot_dispatch_form=kwargs.get('bot_dispatch_form'),
                gmail_dispatch_form=kwargs.get('gmail_dispatch_form'),
            )
        )
        context.update(
            {
                'bot_dispatch_action_url': reverse('dispatch_flow:create_bot_conversa_dispatch'),
                'gmail_dispatch_action_url': reverse('dispatch_flow:create_gmail_dispatch'),
            }
        )
        return context


class DispatchFlowBotConversaCreateView(DispatchFlowAccessMixin, View):
    def post(self, request, *args, **kwargs):
        if not DispatchFlowAccessService.is_app_installed(
            organization=self.active_organization,
            app_code=DispatchFlowAccessService.BOT_CONVERSA_CODE,
        ):
            messages.error(request, 'O Bot Conversa nao esta instalado na organizacao ativa.')
            return redirect('dispatch_flow:index')

        form = BotConversaDispatchWorkspaceService.build_dispatch_form(
            request.POST,
            organization=self.active_organization,
            selected_tag_public_ids=request.POST.getlist('tag_public_ids'),
        )
        if not form.is_valid():
            view = DispatchFlowView()
            view.request = request
            view.active_organization = self.active_organization
            view.active_membership = self.active_membership
            return view.render_to_response(view.get_context_data(bot_dispatch_form=form))

        try:
            dispatch = DispatchFlowActionService.create_bot_conversa_dispatch(
                user=request.user,
                organization=self.active_organization,
                flow_public_id=form.cleaned_data['flow_public_id'],
                person_public_ids=form.cleaned_data['person_public_ids'],
                tag_public_ids=form.cleaned_data['tag_public_ids'],
                min_delay_seconds=form.cleaned_data['min_delay_seconds'],
                max_delay_seconds=form.cleaned_data['max_delay_seconds'],
            )
        except DispatchFlowActionService.handled_exceptions() as exc:
            messages.error(request, str(exc))
            return redirect('dispatch_flow:index')

        messages.success(request, 'Disparo do fluxo criado. O processamento continuara na tela de status.')
        return redirect('bot_conversa:dispatch_detail', dispatch_public_id=dispatch.public_id)


class DispatchFlowGmailCreateView(DispatchFlowAccessMixin, View):
    def post(self, request, *args, **kwargs):
        if not DispatchFlowAccessService.is_app_installed(
            organization=self.active_organization,
            app_code=DispatchFlowAccessService.GMAIL_CODE,
        ):
            messages.error(request, 'O Gmail nao esta instalado na organizacao ativa.')
            return redirect('dispatch_flow:index')

        form = GmailDispatchWorkspaceService.build_dispatch_form(
            request.POST,
            organization=self.active_organization,
        )
        if not form.is_valid():
            view = DispatchFlowView()
            view.request = request
            view.active_organization = self.active_organization
            view.active_membership = self.active_membership
            return view.render_to_response(view.get_context_data(gmail_dispatch_form=form))

        try:
            dispatch = DispatchFlowActionService.create_gmail_dispatch(
                user=request.user,
                organization=self.active_organization,
                template_public_id=form.cleaned_data['template_public_id'],
                person_public_ids=form.cleaned_data['person_public_ids'],
                cc_emails=form.cleaned_data['cc_emails'],
                min_delay_seconds=form.cleaned_data['min_delay_seconds'],
                max_delay_seconds=form.cleaned_data['max_delay_seconds'],
            )
        except DispatchFlowActionService.handled_exceptions() as exc:
            messages.error(request, str(exc))
            return redirect('dispatch_flow:index')

        messages.success(request, 'Disparo do Gmail criado. O processamento continuara na tela de status.')
        return redirect('gmail_integration:dispatch_detail', dispatch_public_id=dispatch.public_id)
