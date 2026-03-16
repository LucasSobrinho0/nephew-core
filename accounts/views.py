from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView

from accounts.forms import LoginForm, RegistrationForm
from accounts.services import AccountService
from common.mixins import AnonymousOnlyMixin
from organizations.services import ActiveOrganizationService


class LoginView(AnonymousOnlyMixin, FormView):
    template_name = 'accounts/login.html'
    form_class = LoginForm
    success_url = reverse_lazy('organizations:onboarding')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        AccountService.login_user(
            self.request,
            form.get_user(),
            form.cleaned_data.get('remember_me', False),
        )
        ActiveOrganizationService.synchronize_request(self.request)
        messages.success(self.request, 'Bem-vindo de volta.')
        return super().form_valid(form)


class RegisterView(AnonymousOnlyMixin, FormView):
    template_name = 'accounts/register.html'
    form_class = RegistrationForm
    success_url = reverse_lazy('accounts:login')

    def form_valid(self, form):
        AccountService.register_user(
            full_name=form.cleaned_data['full_name'],
            email=form.cleaned_data['email'],
            password=form.cleaned_data['password1'],
        )
        messages.success(self.request, 'Sua conta foi criada. Faça login para continuar.')
        return super().form_valid(form)


class LogoutView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        logout(request)
        messages.info(request, 'Voce saiu da sua conta.')
        return redirect('accounts:login')
