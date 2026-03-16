from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect

from organizations.models import OrganizationMembership


class AnonymousOnlyMixin:
    authenticated_redirect_url = 'dashboard:home'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(self.authenticated_redirect_url)
        return super().dispatch(request, *args, **kwargs)


class ActiveOrganizationRequiredMixin(LoginRequiredMixin):
    missing_organization_message = 'Escolha ou crie uma organizacao antes de acessar esta area.'
    missing_organization_redirect_url = 'dashboard:home'

    def dispatch(self, request, *args, **kwargs):
        if not getattr(request, 'active_organization', None):
            messages.info(request, self.missing_organization_message)
            return redirect(self.missing_organization_redirect_url)
        return super().dispatch(request, *args, **kwargs)


class OrganizationRoleRequiredMixin(ActiveOrganizationRequiredMixin):
    allowed_roles = ()
    permission_denied_message = 'Voce nao tem permissao para realizar esta acao na organizacao ativa.'
    permission_denied_redirect_url = 'dashboard:home'

    def dispatch(self, request, *args, **kwargs):
        active_organization = getattr(request, 'active_organization', None)
        if not active_organization:
            messages.info(request, self.missing_organization_message)
            return redirect(self.missing_organization_redirect_url)

        active_membership = getattr(request, 'active_membership', None)
        if not active_membership or active_membership.role not in self.allowed_roles:
            messages.error(request, self.permission_denied_message)
            return redirect(self.permission_denied_redirect_url)

        return super(ActiveOrganizationRequiredMixin, self).dispatch(request, *args, **kwargs)


class InviteManagerRequiredMixin(OrganizationRoleRequiredMixin):
    allowed_roles = (
        OrganizationMembership.Role.OWNER,
        OrganizationMembership.Role.ADMIN,
    )


class OrganizationManagerRequiredMixin(OrganizationRoleRequiredMixin):
    allowed_roles = (
        OrganizationMembership.Role.OWNER,
        OrganizationMembership.Role.ADMIN,
    )
