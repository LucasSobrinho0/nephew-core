from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from common.mixins import ActiveOrganizationRequiredMixin
from companies.forms import CompanyCreateForm, CompanyUpdateForm
from companies.repositories import CompanyRepository
from companies.services import CompanyService
from integrations.repositories import AppCatalogRepository, AppInstallationRepository


class CompanyFeatureSupportMixin:
    @staticmethod
    def _is_app_installed(*, organization, app_code):
        app = AppCatalogRepository.get_by_code(app_code)
        if app is None:
            return False
        installation = AppInstallationRepository.get_for_organization_and_app(organization, app)
        return bool(installation and installation.is_installed)

    def build_feature_flags(self):
        organization = self.request.active_organization
        return {
            'show_hubspot_fields': self._is_app_installed(organization=organization, app_code='hubspot'),
            'show_apollo_fields': self._is_app_installed(organization=organization, app_code='apollo'),
        }

    def build_form_kwargs(self):
        feature_flags = self.build_feature_flags()
        return {
            'show_hubspot_fields': feature_flags['show_hubspot_fields'],
            'show_apollo_fields': feature_flags['show_apollo_fields'],
        }


class CompanyListView(ActiveOrganizationRequiredMixin, CompanyFeatureSupportMixin, TemplateView):
    template_name = 'companies/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        should_load_companies = self.request.GET.get('load') == '1'
        feature_flags = self.build_feature_flags()
        context.update(
            {
                'company_rows': (
                    CompanyRepository.list_for_organization(self.request.active_organization)
                    if should_load_companies
                    else []
                ),
                'has_loaded_companies': should_load_companies,
                'create_form': kwargs.get('create_form') or CompanyCreateForm(**self.build_form_kwargs()),
                **feature_flags,
            }
        )
        return context


class CompanyCreateView(ActiveOrganizationRequiredMixin, CompanyFeatureSupportMixin, View):
    def post(self, request, *args, **kwargs):
        form = CompanyCreateForm(request.POST, **self.build_form_kwargs())
        if not form.is_valid():
            view = CompanyListView()
            view.request = request
            view.args = args
            view.kwargs = kwargs
            return view.render_to_response(view.get_context_data(create_form=form))

        try:
            CompanyService.create_company(
                user=request.user,
                organization=request.active_organization,
                name=form.cleaned_data['name'],
                website=form.cleaned_data.get('website', ''),
                email=form.cleaned_data.get('email', ''),
                phone=form.cleaned_data.get('phone', ''),
                segment=form.cleaned_data.get('segment', ''),
                employee_count=form.cleaned_data.get('employee_count'),
                apollo_company_id=form.cleaned_data.get('apollo_company_id', ''),
                hubspot_company_id=form.cleaned_data.get('hubspot_company_id', ''),
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if exc.messages else str(exc))
            return redirect('companies:index')

        messages.success(request, 'Empresa cadastrada com sucesso.')
        return redirect('companies:index')


class CompanyUpdateView(ActiveOrganizationRequiredMixin, CompanyFeatureSupportMixin, TemplateView):
    template_name = 'companies/edit.html'

    def get_company(self):
        return CompanyRepository.get_for_organization_and_public_id(
            self.request.active_organization,
            self.kwargs['company_public_id'],
        )

    def dispatch(self, request, *args, **kwargs):
        self.company = self.get_company()
        if self.company is None:
            messages.error(request, 'A empresa selecionada nao foi encontrada.')
            return redirect('companies:index')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        feature_flags = self.build_feature_flags()
        form = kwargs.get('form') or CompanyUpdateForm(
            initial={
                'name': self.company.name,
                'website': self.company.website,
                'email': self.company.email,
                'phone': self.company.phone,
                'segment': self.company.segment,
                'employee_count': self.company.employee_count,
                'hubspot_company_id': self.company.hubspot_company_id,
                'apollo_company_id': self.company.apollo_company_id,
            },
            **self.build_form_kwargs(),
        )
        context.update(
            {
                'company': self.company,
                'form': form,
                **feature_flags,
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        form = CompanyUpdateForm(request.POST, **self.build_form_kwargs())
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        try:
            CompanyService.update_company(
                user=request.user,
                organization=request.active_organization,
                company=self.company,
                name=form.cleaned_data['name'],
                website=form.cleaned_data.get('website', ''),
                email=form.cleaned_data.get('email', ''),
                phone=form.cleaned_data.get('phone', ''),
                segment=form.cleaned_data.get('segment', ''),
                employee_count=form.cleaned_data.get('employee_count'),
                apollo_company_id=form.cleaned_data.get('apollo_company_id', ''),
                hubspot_company_id=form.cleaned_data.get('hubspot_company_id', ''),
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if exc.messages else str(exc))
            return self.render_to_response(self.get_context_data(form=form))

        messages.success(request, 'Empresa atualizada com sucesso.')
        return redirect('companies:index')
