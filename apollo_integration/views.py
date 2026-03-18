from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import QueryDict
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apollo_integration.exceptions import ApolloApiError, ApolloConfigurationError
from apollo_integration.forms import (
    ApolloBulkCompanyHubSpotSyncForm,
    ApolloBulkRemoteCompanyImportForm,
    ApolloLocalCompanyListForm,
    ApolloOrganizationSearchForm,
)
from apollo_integration.services import (
    ApolloCompanyService,
    ApolloDashboardService,
    ApolloInstallationService,
)
from companies.repositories import CompanyRepository


class ApolloAccessMixin(LoginRequiredMixin):
    missing_organization_message = 'Escolha ou crie uma organizacao antes de acessar o Apollo.'
    missing_organization_redirect_url = 'dashboard:home'
    missing_installation_redirect_url = 'integrations:apps'

    def prepare_request_context(self, request):
        active_organization = getattr(request, 'active_organization', None)
        active_membership = getattr(request, 'active_membership', None)

        if active_organization is None:
            messages.info(request, self.missing_organization_message)
            return redirect(self.missing_organization_redirect_url)

        if active_membership is None:
            messages.error(request, 'Voce nao tem mais acesso a organizacao ativa.')
            return redirect(self.missing_organization_redirect_url)

        try:
            self.installation = ApolloInstallationService.get_installation(organization=active_organization)
        except (ApolloConfigurationError, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect(self.missing_installation_redirect_url)

        self.active_organization = active_organization
        self.active_membership = active_membership
        return None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        redirect_response = self.prepare_request_context(request)
        if redirect_response is not None:
            return redirect_response
        return super().dispatch(request, *args, **kwargs)

    def build_company_choices(self):
        return ApolloCompanyService.build_company_choice_rows(organization=self.active_organization)

    def build_base_context(self, *, active_tab):
        return {
            'apollo_tabs': [
                {'label': 'Visao geral', 'url': 'apollo_integration:dashboard', 'key': 'dashboard'},
                {'label': 'Empresas', 'url': 'apollo_integration:companies', 'key': 'companies'},
            ],
            'apollo_active_tab': active_tab,
            'can_manage_apollo': self.active_membership.can_manage_integrations,
        }

    @staticmethod
    def build_url_with_query(route_name, query_string=''):
        base_url = reverse(route_name)
        if not query_string:
            return base_url
        return f'{base_url}?{query_string}'


class ApolloOperatorRequiredMixin(ApolloAccessMixin):
    permission_denied_message = 'Somente proprietarios e administradores podem operar acoes do Apollo.'
    permission_denied_redirect_url = 'apollo_integration:dashboard'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        redirect_response = self.prepare_request_context(request)
        if redirect_response is not None:
            return redirect_response

        if not self.active_membership.can_manage_integrations:
            messages.error(request, self.permission_denied_message)
            return redirect(self.permission_denied_redirect_url)

        return super(ApolloAccessMixin, self).dispatch(request, *args, **kwargs)


class ApolloDashboardView(ApolloAccessMixin, TemplateView):
    template_name = 'apollo_integration/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.build_base_context(active_tab='dashboard'))
        try:
            context['summary'] = ApolloDashboardService.build_summary(organization=self.active_organization)
        except ApolloConfigurationError as exc:
            messages.error(self.request, str(exc))
            context['summary'] = {
                'installation': self.installation,
                'company_count': CompanyRepository.list_for_organization(self.active_organization).count(),
                'synced_company_count': 0,
                'recent_sync_logs': [],
                'usage': {
                    'available': False,
                    'message': str(exc),
                    'credit_summary': [],
                    'rate_limits': [],
                    'raw_payload': {},
                },
            }
        return context


class ApolloCompaniesView(ApolloAccessMixin, TemplateView):
    template_name = 'apollo_integration/companies.html'

    @staticmethod
    def _has_remote_search_request(query_dict):
        if query_dict.get('search') == '1':
            return True
        filter_keys = (
            'q_organization_name',
            'q_organization_domains',
            'organization_locations',
            'organization_industries',
            'organization_num_employees_ranges',
            'page',
            'per_page',
        )
        return any(query_dict.getlist(key) if key == 'organization_num_employees_ranges' else query_dict.get(key) for key in filter_keys)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        load_local_form = ApolloLocalCompanyListForm(self.request.GET or None)
        search_form = kwargs.get('search_form') or ApolloOrganizationSearchForm(self.request.GET or None)
        company_rows = []
        remote_companies = []
        pagination = {}
        search_diagnostics = {}
        has_loaded_local_companies = self.request.GET.get('load_local') == '1'
        has_loaded_remote_companies = self._has_remote_search_request(self.request.GET)

        if has_loaded_local_companies and load_local_form.is_valid():
            company_rows = ApolloCompanyService.build_company_rows(organization=self.active_organization)

        if has_loaded_remote_companies and search_form.is_valid():
            try:
                remote_result = ApolloCompanyService.list_remote_companies(
                    organization=self.active_organization,
                    filters=search_form.cleaned_data,
                )
                remote_companies = remote_result['companies']
                pagination = remote_result['pagination']
                search_diagnostics = remote_result.get('diagnostics') or {}
            except (ApolloApiError, ApolloConfigurationError, ValidationError) as exc:
                messages.error(self.request, str(exc))

        context.update(self.build_base_context(active_tab='companies'))
        context.update(
            {
                'load_local_form': load_local_form,
                'search_form': search_form,
                'company_rows': company_rows,
                'remote_companies': remote_companies,
                'pagination': pagination,
                'search_diagnostics': search_diagnostics,
                'has_loaded_local_companies': has_loaded_local_companies,
                'has_loaded_remote_companies': has_loaded_remote_companies,
                'current_remote_query': self.request.GET.urlencode(),
            }
        )
        return context


class ApolloBulkRemoteCompanyImportView(ApolloOperatorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        current_query = request.POST.get('current_query', '')
        search_data = QueryDict(current_query) if current_query else request.POST
        search_form = ApolloOrganizationSearchForm(search_data)
        search_form.is_valid()
        remote_result = ApolloCompanyService.list_remote_companies(
            organization=self.active_organization,
            filters=search_form.cleaned_data if search_form.cleaned_data else {},
        )
        choices = [(company['apollo_company_id'], company['name']) for company in remote_result['companies']]
        form = ApolloBulkRemoteCompanyImportForm(request.POST, company_choices=choices)

        if not form.is_valid():
            messages.error(request, form.errors.get('apollo_company_ids', ['Selecione empresas remotas validas.'])[0])
            return redirect(self.build_url_with_query('apollo_integration:companies', current_query))

        selected_ids = set(form.cleaned_data['apollo_company_ids'])
        selected_companies = [
            company
            for company in remote_result['companies']
            if company['apollo_company_id'] in selected_ids
        ]

        try:
            ApolloCompanyService.import_remote_companies(
                user=request.user,
                organization=self.active_organization,
                remote_companies=selected_companies,
            )
        except (ApolloApiError, ApolloConfigurationError, PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect(self.build_url_with_query('apollo_integration:companies', current_query))

        messages.success(request, f'{len(selected_companies)} empresas do Apollo foram salvas no CRM.')
        return redirect(self.build_url_with_query('apollo_integration:companies', current_query))


class ApolloBulkCompanyHubSpotSyncView(ApolloAccessMixin, View):
    def post(self, request, *args, **kwargs):
        form = ApolloBulkCompanyHubSpotSyncForm(request.POST, company_choices=self.build_company_choices())
        if not form.is_valid():
            messages.error(request, form.errors.get('company_public_ids', ['Selecione empresas validas.'])[0])
            return redirect(self.build_url_with_query('apollo_integration:companies', 'load_local=1'))

        companies = list(
            CompanyRepository.list_for_organization_and_public_ids(
                self.active_organization,
                form.cleaned_data['company_public_ids'],
            )
        )
        try:
            ApolloCompanyService.sync_companies_to_hubspot(
                user=request.user,
                organization=self.active_organization,
                companies=companies,
            )
        except (ApolloApiError, ApolloConfigurationError, PermissionDenied, ValidationError, Exception) as exc:
            messages.error(request, str(exc))
            return redirect(self.build_url_with_query('apollo_integration:companies', 'load_local=1'))

        messages.success(request, f'{len(companies)} empresas foram sincronizadas com o HubSpot.')
        return redirect(self.build_url_with_query('apollo_integration:companies', 'load_local=1'))
