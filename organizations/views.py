from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import TemplateView

from common.mixins import InviteManagerRequiredMixin
from organizations.forms import InviteGenerationForm, InviteRedeemForm, OrganizationCreateForm, OrganizationSwitchForm
from organizations.repositories import InviteRepository, MembershipRepository
from organizations.services import InviteService, OrganizationService


class OnboardingContextMixin:
    template_name = 'organizations/onboarding.html'

    def build_onboarding_context(self, *, step='choice', create_form=None, join_form=None):
        memberships = OrganizationService.list_user_memberships(self.request.user)
        return {
            'step': step,
            'create_form': create_form or OrganizationCreateForm(),
            'join_form': join_form or InviteRedeemForm(),
            'memberships': memberships,
        }

    def render_onboarding(self, *, step='choice', create_form=None, join_form=None):
        context = self.build_onboarding_context(
            step=step,
            create_form=create_form,
            join_form=join_form,
        )
        return render(self.request, self.template_name, context)


class OnboardingView(LoginRequiredMixin, OnboardingContextMixin, TemplateView):
    template_name = 'organizations/onboarding.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        step = self.request.GET.get('step', 'choice')
        if step not in {'choice', 'create', 'join'}:
            step = 'choice'
        context.update(self.build_onboarding_context(step=step))
        return context


class OnboardingCreateOrganizationView(LoginRequiredMixin, OnboardingContextMixin, View):
    def post(self, request, *args, **kwargs):
        form = OrganizationCreateForm(request.POST)
        if not form.is_valid():
            return self.render_onboarding(step='create', create_form=form)

        organization = OrganizationService.create_organization_for_user(
            user=request.user,
            name=form.cleaned_data['name'],
            segment=form.cleaned_data['segment'],
            team_size=form.cleaned_data['team_size'],
        )
        OrganizationService.switch_active_organization(
            request=request,
            user=request.user,
            organization_public_id=organization.public_id,
        )

        messages.success(request, 'Organizacao criada com sucesso.')
        return redirect('dashboard:home')


class OnboardingJoinOrganizationView(LoginRequiredMixin, OnboardingContextMixin, View):
    def post(self, request, *args, **kwargs):
        form = InviteRedeemForm(request.POST)
        if not form.is_valid():
            return self.render_onboarding(step='join', join_form=form)

        try:
            InviteService.redeem_invite(
                request=request,
                user=request.user,
                raw_code=form.cleaned_data['code'],
            )
        except PermissionDenied as exc:
            form.add_error('code', str(exc))
            return self.render_onboarding(step='join', join_form=form)
        except Exception as exc:
            message = exc.messages[0] if hasattr(exc, 'messages') and exc.messages else str(exc)
            form.add_error('code', message)
            return self.render_onboarding(step='join', join_form=form)

        messages.success(request, 'Voce entrou na organizacao com sucesso.')
        return redirect('dashboard:home')


class OrganizationsView(LoginRequiredMixin, TemplateView):
    template_name = 'organizations/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_organization = getattr(self.request, 'active_organization', None)
        active_membership = getattr(self.request, 'active_membership', None)
        memberships = OrganizationService.list_user_memberships(self.request.user)
        members = MembershipRepository.list_for_organization(active_organization) if active_organization else []

        context.update(
            {
                'memberships': memberships,
                'members': members,
                'switch_form': OrganizationSwitchForm(),
                'can_manage_invites': active_membership.can_manage_invites if active_membership else False,
            }
        )
        return context


class SwitchActiveOrganizationView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = OrganizationSwitchForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Selecione uma organizacao valida.')
            return redirect('organizations:index')

        try:
            OrganizationService.switch_active_organization(
                request=request,
                user=request.user,
                organization_public_id=form.cleaned_data['organization_public_id'],
            )
        except PermissionDenied:
            messages.error(request, 'Voce nao pode trocar para uma organizacao da qual nao faz parte.')
            return redirect('organizations:index')

        messages.success(request, 'Organizacao ativa atualizada.')
        return redirect(request.POST.get('next') or 'organizations:index')


class InviteListView(InviteManagerRequiredMixin, TemplateView):
    template_name = 'organizations/invites.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_organization = self.request.active_organization
        InviteService.expire_outdated_invites(active_organization)

        context.update(
            {
                'invites': InviteRepository.list_for_organization(active_organization),
                'generate_form': InviteGenerationForm(),
                'available_count': InviteRepository.count_by_status(active_organization, 'available'),
                'used_count': InviteRepository.count_by_status(active_organization, 'used'),
                'expired_count': InviteRepository.count_by_status(active_organization, 'expired'),
            }
        )
        return context


class InviteGenerateView(InviteManagerRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = InviteGenerationForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Escolha um tipo de convite valido.')
            return redirect('organizations:invites')

        try:
            InviteService.generate_invite(
                user=request.user,
                organization=request.active_organization,
                target_role=form.cleaned_data['target_role'],
            )
        except PermissionDenied:
            messages.error(request, 'Voce nao tem permissao para gerar codigos de convite.')
            return redirect('dashboard:home')

        messages.success(request, 'Codigo de convite criado com sucesso.')
        return redirect('organizations:invites')
