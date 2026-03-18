import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, JsonResponse, QueryDict
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from apollo_integration.exceptions import ApolloApiError, ApolloConfigurationError
from apollo_integration.forms import (
    ApolloBulkCompanyHubSpotSyncForm,
    ApolloPeopleEnrichmentForm,
    ApolloBulkRemoteCompanyImportForm,
    ApolloBulkRemotePersonImportForm,
    ApolloLocalCompanyListForm,
    ApolloOrganizationSearchForm,
    ApolloPeopleSearchForm,
)
from apollo_integration.services import (
    ApolloCompanyService,
    ApolloDashboardService,
    ApolloInstallationService,
    ApolloPersonService,
)
from apollo_integration.repositories import ApolloPeopleEnrichmentJobRepository
from companies.repositories import CompanyRepository
from people.repositories import PersonRepository


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
                {'label': 'Pessoas', 'url': 'apollo_integration:people', 'key': 'people'},
                {'label': 'Enriquecimento', 'url': 'apollo_integration:enrichment', 'key': 'enrichment'},
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

    def build_pagination_links(self, *, route_name, current_page, total_pages):
        if total_pages <= 1:
            return {}

        def build_query_for_page(page_number):
            query = self.request.GET.copy()
            query['search'] = '1'
            query['page'] = str(page_number)
            return query.urlencode()

        page_numbers = []
        start_page = max(1, current_page - 2)
        end_page = min(total_pages, current_page + 2)
        for page_number in range(start_page, end_page + 1):
            page_numbers.append(
                {
                    'number': page_number,
                    'is_current': page_number == current_page,
                    'url': self.build_url_with_query(route_name, build_query_for_page(page_number)),
                }
            )

        return {
            'current_page': current_page,
            'total_pages': total_pages,
            'previous_url': (
                self.build_url_with_query(route_name, build_query_for_page(current_page - 1))
                if current_page > 1
                else ''
            ),
            'next_url': (
                self.build_url_with_query(route_name, build_query_for_page(current_page + 1))
                if current_page < total_pages
                else ''
            ),
            'page_numbers': page_numbers,
        }


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
        pagination_links = {}
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
                current_page = int(search_form.cleaned_data.get('page') or 1)
                total_pages = int((pagination.get('total_pages') or current_page) or current_page)
                pagination_links = self.build_pagination_links(
                    route_name='apollo_integration:companies',
                    current_page=current_page,
                    total_pages=total_pages,
                )
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
                'pagination_links': pagination_links,
                'has_loaded_local_companies': has_loaded_local_companies,
                'has_loaded_remote_companies': has_loaded_remote_companies,
                'current_remote_query': self.request.GET.urlencode(),
            }
        )
        return context


class ApolloPeopleView(ApolloAccessMixin, TemplateView):
    template_name = 'apollo_integration/people.html'

    @staticmethod
    def _has_remote_search_request(query_dict):
        if query_dict.get('search') == '1':
            return True
        filter_keys = (
            'company_public_id',
            'q_organization_name',
            'q_organization_domains',
            'person_titles',
            'q_keywords',
            'contact_email_status',
            'page',
            'per_page',
        )
        return any(query_dict.get(key) for key in filter_keys)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_form = kwargs.get('search_form') or ApolloPeopleSearchForm(
            self.request.GET or None,
            company_choices=ApolloPersonService.build_company_filter_choices(organization=self.active_organization),
        )
        person_rows = []
        remote_people = []
        pagination = {}
        pagination_links = {}
        has_loaded_local_people = self.request.GET.get('load_local') == '1'
        has_loaded_remote_people = self._has_remote_search_request(self.request.GET)

        if has_loaded_local_people:
            person_rows = ApolloPersonService.build_person_rows(organization=self.active_organization)

        if has_loaded_remote_people and search_form.is_valid():
            try:
                remote_result = ApolloPersonService.list_remote_people(
                    organization=self.active_organization,
                    filters=search_form.cleaned_data,
                )
                remote_people = remote_result['people']
                pagination = remote_result['pagination']
                current_page = int(search_form.cleaned_data.get('page') or 1)
                total_pages = int((pagination.get('total_pages') or current_page) or current_page)
                pagination_links = self.build_pagination_links(
                    route_name='apollo_integration:people',
                    current_page=current_page,
                    total_pages=total_pages,
                )
            except (ApolloApiError, ApolloConfigurationError, ValidationError) as exc:
                messages.error(self.request, str(exc))

        context.update(self.build_base_context(active_tab='people'))
        context.update(
            {
                'search_form': search_form,
                'person_rows': person_rows,
                'remote_people': remote_people,
                'pagination': pagination,
                'pagination_links': pagination_links,
                'has_loaded_local_people': has_loaded_local_people,
                'has_loaded_remote_people': has_loaded_remote_people,
                'current_remote_query': self.request.GET.urlencode(),
            }
        )
        return context


class ApolloPeopleEnrichmentView(ApolloAccessMixin, TemplateView):
    template_name = 'apollo_integration/enrichment.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        enrichment_rows = ApolloPersonService.build_enrichment_rows(organization=self.active_organization)
        context.update(self.build_base_context(active_tab='enrichment'))
        context.update(
            {
                'enrichment_rows': enrichment_rows,
                'enrichment_form': kwargs.get('enrichment_form') or ApolloPeopleEnrichmentForm(
                    person_choices=[(str(row['person'].public_id), row['person'].full_name) for row in enrichment_rows]
                ),
                'recent_enrichment_jobs': ApolloPersonService.build_recent_enrichment_jobs(
                    organization=self.active_organization
                ),
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
        selected_ids = [value.strip() for value in request.POST.getlist('apollo_company_ids') if value.strip()]
        if not selected_ids:
            messages.error(request, 'Selecione pelo menos uma empresa remota para salvar.')
            return redirect(self.build_url_with_query('apollo_integration:companies', current_query))

        selected_ids = set(selected_ids)
        selected_companies = [
            company
            for company in remote_result['companies']
            if company['apollo_company_id'] in selected_ids
        ]

        if not selected_companies:
            messages.error(
                request,
                'A listagem remota mudou antes do salvamento. Atualize a busca e selecione novamente as empresas desejadas.',
            )
            return redirect(self.build_url_with_query('apollo_integration:companies', current_query))

        if len(selected_companies) != len(selected_ids):
            messages.warning(
                request,
                'Algumas empresas selecionadas nao estavam mais na listagem atual e foram ignoradas.',
            )

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


class ApolloBulkRemotePersonImportView(ApolloOperatorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        current_query = request.POST.get('current_query', '')
        search_data = QueryDict(current_query) if current_query else request.POST
        search_form = ApolloPeopleSearchForm(
            search_data,
            company_choices=ApolloPersonService.build_company_filter_choices(organization=self.active_organization),
        )
        search_form.is_valid()
        remote_result = ApolloPersonService.list_remote_people(
            organization=self.active_organization,
            filters=search_form.cleaned_data if search_form.cleaned_data else {},
        )
        selected_ids = [value.strip() for value in request.POST.getlist('apollo_person_ids') if value.strip()]
        if not selected_ids:
            messages.error(request, 'Selecione pelo menos uma pessoa remota para salvar.')
            return redirect(self.build_url_with_query('apollo_integration:people', current_query))

        selected_ids = set(selected_ids)
        selected_people = [
            person
            for person in remote_result['people']
            if person['apollo_person_id'] in selected_ids
        ]

        if not selected_people:
            messages.error(
                request,
                'A listagem remota mudou antes do salvamento. Atualize a busca e selecione novamente as pessoas desejadas.',
            )
            return redirect(self.build_url_with_query('apollo_integration:people', current_query))

        if len(selected_people) != len(selected_ids):
            messages.warning(
                request,
                'Algumas pessoas selecionadas nao estavam mais na listagem atual e foram ignoradas.',
            )

        try:
            ApolloPersonService.import_remote_people(
                user=request.user,
                organization=self.active_organization,
                remote_people=selected_people,
            )
        except (ApolloApiError, ApolloConfigurationError, PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect(self.build_url_with_query('apollo_integration:people', current_query))

        messages.success(request, f'{len(selected_people)} pessoas do Apollo foram salvas no CRM.')
        return redirect(self.build_url_with_query('apollo_integration:people', current_query))


class ApolloBulkPeopleEnrichmentView(ApolloOperatorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        enrichment_rows = ApolloPersonService.build_enrichment_rows(organization=self.active_organization)
        form = ApolloPeopleEnrichmentForm(
            request.POST,
            person_choices=[(str(row['person'].public_id), row['person'].full_name) for row in enrichment_rows],
        )
        if not form.is_valid():
            view = ApolloPeopleEnrichmentView()
            view.request = request
            view.args = args
            view.kwargs = kwargs
            view.installation = self.installation
            view.active_organization = self.active_organization
            view.active_membership = self.active_membership
            return view.render_to_response(view.get_context_data(enrichment_form=form))

        people = list(
            PersonRepository.list_for_organization_and_public_ids(
                self.active_organization,
                form.cleaned_data['person_public_ids'],
            )
        )
        people = [person for person in people if person.apollo_person_id]
        try:
            result = ApolloPersonService.enrich_people(
                user=request.user,
                organization=self.active_organization,
                people=people,
                fetch_phone=form.cleaned_data['fetch_phone'],
                request=request,
            )
        except (ApolloApiError, ApolloConfigurationError, PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect('apollo_integration:enrichment')

        if result['fetch_phone']:
            messages.success(
                request,
                (
                    f"{result['enriched_count']} pessoa(s) foram atualizadas agora e o job de telefone "
                    'ficou aguardando webhook do Apollo.'
                ),
            )
        else:
            messages.success(
                request,
                (
                    f"{result['enriched_count']} pessoa(s) foram atualizadas com nome completo e e-mail "
                    f'a partir do Apollo.'
                ),
            )
        return redirect('apollo_integration:enrichment')


@method_decorator(csrf_exempt, name='dispatch')
class ApolloPeopleEnrichmentWebhookView(View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        job = ApolloPeopleEnrichmentJobRepository.get_for_public_id(kwargs['job_public_id'])
        if job is None:
            raise Http404('Job de enrichment nao encontrado.')

        token = (request.GET.get('token') or '').strip()
        if not token or token != job.webhook_token:
            return JsonResponse({'detail': 'Webhook token invalido.'}, status=403)

        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except (TypeError, ValueError):
            return JsonResponse({'detail': 'Payload JSON invalido.'}, status=400)

        try:
            ApolloPersonService.process_enrichment_webhook(job=job, payload=payload)
        except ValidationError as exc:
            return JsonResponse({'detail': str(exc)}, status=400)

        return JsonResponse({'detail': 'Webhook processado.'}, status=200)


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
