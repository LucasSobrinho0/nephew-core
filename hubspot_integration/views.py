from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from companies.repositories import CompanyRepository
from hubspot_integration.forms import (
    HubSpotBulkCompanySyncForm,
    HubSpotBulkPersonSyncForm,
    HubSpotBulkRemoteCompanyImportForm,
    HubSpotBulkRemoteContactImportForm,
    HubSpotCompanyCreateForm,
    HubSpotContactCompanySyncForm,
    HubSpotCompanySyncForm,
    HubSpotDealCreateForm,
    HubSpotPersonCreateForm,
    HubSpotPersonSyncForm,
    HubSpotPipelineRefreshForm,
    HubSpotRemoteCompanyImportForm,
    HubSpotRemoteContactImportForm,
    HubSpotRemoteListForm,
)
from hubspot_integration.repositories import HubSpotDealRepository, HubSpotPipelineRepository
from hubspot_integration.services import (
    HubSpotCompanyService,
    HubSpotContactService,
    HubSpotDashboardService,
    HubSpotDealService,
    HubSpotInstallationService,
    HubSpotPipelineService,
)
from people.repositories import PersonRepository


class HubSpotAccessMixin(LoginRequiredMixin, TemplateView):
    missing_organization_message = 'Escolha ou crie uma organização antes de acessar o HubSpot.'
    missing_organization_redirect_url = 'dashboard:home'
    missing_installation_redirect_url = 'integrations:apps'

    def prepare_request_context(self, request):
        active_organization = getattr(request, 'active_organization', None)
        active_membership = getattr(request, 'active_membership', None)

        if active_organization is None:
            messages.info(request, self.missing_organization_message)
            return redirect(self.missing_organization_redirect_url)
        if active_membership is None:
            messages.error(request, 'Você não tem mais acesso à organização ativa.')
            return redirect(self.missing_organization_redirect_url)
        try:
            self.installation = HubSpotInstallationService.get_installation(organization=active_organization)
        except ValidationError as exc:
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
        return HubSpotCompanyService.build_company_choice_rows(organization=self.active_organization)

    def build_synced_company_choices(self):
        return [
            (str(company.public_id), company.name)
            for company in CompanyRepository.list_for_organization(self.active_organization)
            if company.hubspot_company_id
        ]

    def build_person_choices(self):
        return HubSpotContactService.build_person_choice_rows(organization=self.active_organization)

    def build_pipeline_choices(self):
        return [
            (str(pipeline.public_id), pipeline.name)
            for pipeline in HubSpotPipelineRepository.list_for_organization(self.active_organization)
        ]

    def build_stage_choices(self):
        return HubSpotPipelineService.build_stage_choices(organization=self.active_organization)

    def build_base_context(self, *, active_tab):
        return {
            'hubspot_tabs': [
                {'label': 'Visão geral', 'url': 'hubspot_integration:dashboard', 'key': 'dashboard'},
                {'label': 'Empresas', 'url': 'hubspot_integration:companies', 'key': 'companies'},
                {'label': 'Pessoas', 'url': 'hubspot_integration:people', 'key': 'people'},
                {'label': 'Pipelines', 'url': 'hubspot_integration:pipelines', 'key': 'pipelines'},
                {'label': 'Negócios', 'url': 'hubspot_integration:deals', 'key': 'deals'},
            ],
            'hubspot_active_tab': active_tab,
            'can_manage_hubspot': self.active_membership.can_manage_integrations,
        }

    def build_url_with_query(self, route_name, query_string=''):
        base_url = reverse(route_name)
        if not query_string:
            return base_url
        return f'{base_url}?{query_string}'


class HubSpotDashboardView(HubSpotAccessMixin):
    template_name = 'hubspot_integration/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.build_base_context(active_tab='dashboard'))
        context['summary'] = HubSpotDashboardService.build_summary(organization=self.active_organization)
        return context


class HubSpotCompaniesView(HubSpotAccessMixin):
    template_name = 'hubspot_integration/companies.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        load_form = HubSpotRemoteListForm(self.request.GET or None)
        remote_companies = []
        company_rows = []
        has_loaded_local_companies = self.request.GET.get('load_local') == '1'
        has_loaded_remote_companies = False

        if has_loaded_local_companies:
            company_rows = HubSpotCompanyService.build_company_rows(organization=self.active_organization)

        if self.request.GET.get('load') == '1' and load_form.is_valid():
            has_loaded_remote_companies = True
            try:
                remote_companies = HubSpotCompanyService.list_remote_companies(organization=self.active_organization)
            except Exception as exc:
                messages.error(self.request, str(exc))

        context.update(self.build_base_context(active_tab='companies'))
        context.update(
            {
                'company_rows': company_rows,
                'has_loaded_local_companies': has_loaded_local_companies,
                'remote_companies': remote_companies,
                'has_loaded_remote_companies': has_loaded_remote_companies,
                'remote_list_form': load_form,
                'create_form': kwargs.get('create_form') or HubSpotCompanyCreateForm(
                    pipeline_choices=self.build_pipeline_choices(),
                    stage_choices=self.build_stage_choices(),
                ),
            }
        )
        return context


class HubSpotCompanyCreateView(HubSpotAccessMixin, View):
    def post(self, request, *args, **kwargs):
        form = HubSpotCompanyCreateForm(
            request.POST,
            pipeline_choices=self.build_pipeline_choices(),
            stage_choices=self.build_stage_choices(),
        )
        if not form.is_valid():
            view = HubSpotCompaniesView()
            view.request = request
            view.installation = self.installation
            view.active_organization = self.active_organization
            view.active_membership = self.active_membership
            return view.render_to_response(view.get_context_data(create_form=form))
        try:
            pipeline = None
            if form.cleaned_data.get('create_deal_now'):
                pipeline = HubSpotPipelineRepository.get_for_organization_and_public_id(
                    self.active_organization,
                    form.cleaned_data['pipeline_public_id'],
                )
                if pipeline is None:
                    raise ValidationError('O pipeline selecionado nao foi encontrado.')

            _company, deal = HubSpotCompanyService.create_local_company_with_business(
                user=request.user,
                organization=self.active_organization,
                name=form.cleaned_data['name'],
                website=form.cleaned_data['website'],
                phone=form.cleaned_data['phone'],
                create_deal_now=form.cleaned_data.get('create_deal_now', False),
                deal_name=form.cleaned_data.get('deal_name', ''),
                pipeline=pipeline,
                stage_id=form.cleaned_data.get('stage_id', ''),
                amount=form.cleaned_data.get('amount', ''),
            )
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect('hubspot_integration:companies')
        if deal is not None:
            messages.success(request, 'Empresa e negocio cadastrados com sucesso.')
        else:
            messages.success(request, 'Empresa cadastrada com sucesso.')
        return redirect('hubspot_integration:companies')


class HubSpotCompanySyncView(HubSpotAccessMixin, View):
    def post(self, request, *args, **kwargs):
        form = HubSpotCompanySyncForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Selecione uma empresa válida para sincronizar.')
            return redirect('hubspot_integration:companies')
        company = CompanyRepository.get_for_organization_and_public_id(
            self.active_organization,
            form.cleaned_data['company_public_id'],
        )
        if company is None:
            messages.error(request, 'A empresa selecionada não foi encontrada.')
            return redirect('hubspot_integration:companies')
        try:
            HubSpotCompanyService.sync_companies(
                user=request.user,
                organization=self.active_organization,
                companies=[company],
            )
        except (PermissionDenied, ValidationError, Exception) as exc:
            messages.error(request, str(exc))
            return redirect('hubspot_integration:companies')
        messages.success(request, 'Empresa sincronizada com o HubSpot.')
        return redirect('hubspot_integration:companies')


class HubSpotBulkCompanySyncView(HubSpotAccessMixin, View):
    def post(self, request, *args, **kwargs):
        form = HubSpotBulkCompanySyncForm(request.POST, company_choices=self.build_company_choices())
        if not form.is_valid():
            messages.error(request, form.errors.get('company_public_ids', ['Selecione empresas válidas.'])[0])
            return redirect('hubspot_integration:companies')

        companies = list(
            CompanyRepository.list_for_organization_and_public_ids(
                self.active_organization,
                form.cleaned_data['company_public_ids'],
            )
        )
        try:
            HubSpotCompanyService.sync_companies(
                user=request.user,
                organization=self.active_organization,
                companies=companies,
            )
        except (PermissionDenied, ValidationError, Exception) as exc:
            messages.error(request, str(exc))
            return redirect('hubspot_integration:companies')
        messages.success(request, f'{len(companies)} empresas foram sincronizadas com o HubSpot.')
        return redirect('hubspot_integration:companies')


class HubSpotRemoteCompanyImportView(HubSpotAccessMixin, View):
    def post(self, request, *args, **kwargs):
        form = HubSpotRemoteCompanyImportForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Os dados da empresa remota são inválidos.')
            return redirect('hubspot_integration:companies')
        try:
            HubSpotCompanyService.import_remote_companies(
                user=request.user,
                organization=self.active_organization,
                remote_companies=[
                    {
                        'hubspot_company_id': form.cleaned_data['hubspot_company_id'],
                        'name': form.cleaned_data['name'],
                        'website': form.cleaned_data['website'],
                        'phone': form.cleaned_data['phone'],
                    }
                ],
            )
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect('hubspot_integration:companies')
        messages.success(request, 'Empresa remota salva no CRM.')
        return redirect(self.build_url_with_query('hubspot_integration:companies', 'load=1'))


class HubSpotBulkRemoteCompanyImportView(HubSpotAccessMixin, View):
    def post(self, request, *args, **kwargs):
        remote_companies = HubSpotCompanyService.list_remote_companies(organization=self.active_organization)
        choices = [(company['hubspot_company_id'], company['name']) for company in remote_companies]
        form = HubSpotBulkRemoteCompanyImportForm(request.POST, company_choices=choices)
        if not form.is_valid():
            messages.error(request, form.errors.get('hubspot_company_ids', ['Selecione empresas remotas válidas.'])[0])
            return redirect(self.build_url_with_query('hubspot_integration:companies', 'load=1'))

        selected_ids = set(form.cleaned_data['hubspot_company_ids'])
        selected_companies = [
            company
            for company in remote_companies
            if company['hubspot_company_id'] in selected_ids
        ]
        try:
            HubSpotCompanyService.import_remote_companies(
                user=request.user,
                organization=self.active_organization,
                remote_companies=selected_companies,
            )
        except (PermissionDenied, ValidationError, Exception) as exc:
            messages.error(request, str(exc))
            return redirect(self.build_url_with_query('hubspot_integration:companies', 'load=1'))
        messages.success(request, f'{len(selected_companies)} empresas remotas foram salvas no CRM.')
        return redirect(self.build_url_with_query('hubspot_integration:companies', 'load=1'))


class HubSpotPeopleView(HubSpotAccessMixin):
    template_name = 'hubspot_integration/people.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        load_form = HubSpotRemoteListForm(self.request.GET or None)
        remote_contacts = []
        person_rows = []
        has_loaded_local_people = self.request.GET.get('load_local') == '1'
        has_loaded_remote_contacts = False

        if has_loaded_local_people:
            person_rows = HubSpotContactService.build_person_rows(organization=self.active_organization)

        if self.request.GET.get('load') == '1' and load_form.is_valid():
            has_loaded_remote_contacts = True
            try:
                remote_contacts = HubSpotContactService.list_remote_contacts(organization=self.active_organization)
            except Exception as exc:
                messages.error(self.request, str(exc))

        context.update(self.build_base_context(active_tab='people'))
        context.update(
            {
                'person_rows': person_rows,
                'has_loaded_local_people': has_loaded_local_people,
                'remote_contacts': remote_contacts,
                'has_loaded_remote_contacts': has_loaded_remote_contacts,
                'remote_list_form': load_form,
                'company_sync_form': HubSpotContactCompanySyncForm(),
                'create_form': kwargs.get('create_form') or HubSpotPersonCreateForm(
                    company_choices=self.build_company_choices(),
                    deal_search_url=reverse('hubspot_integration:deal_search'),
                ),
            }
        )
        return context


class HubSpotPersonCreateView(HubSpotAccessMixin, View):
    def post(self, request, *args, **kwargs):
        raw_deal_public_id = (request.POST.get('deal_public_id') or '').strip()
        selected_deal = None
        selected_deal_choice = None

        if raw_deal_public_id:
            selected_deal = HubSpotDealRepository.get_for_organization_and_public_id(
                self.active_organization,
                raw_deal_public_id,
            )
            if selected_deal is not None:
                selected_deal_choice = (
                    str(selected_deal.public_id),
                    f'{selected_deal.name} | {selected_deal.company.name}',
                )

        form = HubSpotPersonCreateForm(
            request.POST,
            company_choices=self.build_company_choices(),
            deal_search_url=reverse('hubspot_integration:deal_search'),
            selected_deal_choice=selected_deal_choice,
        )
        if not form.is_valid():
            view = HubSpotPeopleView()
            view.request = request
            view.installation = self.installation
            view.active_organization = self.active_organization
            view.active_membership = self.active_membership
            return view.render_to_response(view.get_context_data(create_form=form))

        company = None
        if form.cleaned_data['company_public_id']:
            company = CompanyRepository.get_for_organization_and_public_id(
                self.active_organization,
                form.cleaned_data['company_public_id'],
            )

        if raw_deal_public_id and selected_deal is None:
            messages.error(request, 'O negocio selecionado nao foi encontrado.')
            return redirect('hubspot_integration:people')

        try:
            HubSpotContactService.create_local_person(
                user=request.user,
                organization=self.active_organization,
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
                email=form.cleaned_data['email'],
                phone=form.cleaned_data['phone'],
                company=company,
                deal=selected_deal,
            )
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect('hubspot_integration:people')

        if selected_deal is not None:
            messages.success(request, 'Pessoa cadastrada e vinculada ao negocio com sucesso.')
        else:
            messages.success(request, 'Pessoa cadastrada com sucesso.')
        return redirect('hubspot_integration:people')


class HubSpotPersonSyncView(HubSpotAccessMixin, View):
    def post(self, request, *args, **kwargs):
        form = HubSpotPersonSyncForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Selecione uma pessoa válida para sincronizar.')
            return redirect('hubspot_integration:people')
        person = PersonRepository.get_for_organization_and_public_id(
            self.active_organization,
            form.cleaned_data['person_public_id'],
        )
        if person is None:
            messages.error(request, 'A pessoa selecionada não foi encontrada.')
            return redirect('hubspot_integration:people')
        try:
            HubSpotContactService.sync_people(
                user=request.user,
                organization=self.active_organization,
                persons=[person],
            )
        except (PermissionDenied, ValidationError, Exception) as exc:
            messages.error(request, str(exc))
            return redirect('hubspot_integration:people')
        messages.success(request, 'Pessoa sincronizada com o HubSpot.')
        return redirect('hubspot_integration:people')


class HubSpotBulkPersonSyncView(HubSpotAccessMixin, View):
    def post(self, request, *args, **kwargs):
        form = HubSpotBulkPersonSyncForm(request.POST, person_choices=self.build_person_choices())
        if not form.is_valid():
            messages.error(request, form.errors.get('person_public_ids', ['Selecione pessoas válidas.'])[0])
            return redirect('hubspot_integration:people')

        persons = list(
            PersonRepository.list_for_organization_and_public_ids(
                self.active_organization,
                form.cleaned_data['person_public_ids'],
            )
        )
        try:
            HubSpotContactService.sync_people(
                user=request.user,
                organization=self.active_organization,
                persons=persons,
            )
        except (PermissionDenied, ValidationError, Exception) as exc:
            messages.error(request, str(exc))
            return redirect('hubspot_integration:people')
        messages.success(request, f'{len(persons)} pessoas foram sincronizadas com o HubSpot.')
        return redirect('hubspot_integration:people')


class HubSpotRemoteContactImportView(HubSpotAccessMixin, View):
    def post(self, request, *args, **kwargs):
        form = HubSpotRemoteContactImportForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Os dados do contato remoto são inválidos.')
            return redirect('hubspot_integration:people')
        try:
            HubSpotContactService.import_remote_contacts(
                user=request.user,
                organization=self.active_organization,
                remote_contacts=[
                    {
                        'hubspot_contact_id': form.cleaned_data['hubspot_contact_id'],
                        'first_name': form.cleaned_data['first_name'],
                        'last_name': form.cleaned_data['last_name'],
                        'email': form.cleaned_data['email'],
                        'phone': form.cleaned_data['phone'],
                        'company_name': form.cleaned_data['company_name'],
                        'company_hubspot_id': form.cleaned_data['company_hubspot_id'],
                    }
                ],
            )
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect('hubspot_integration:people')
        messages.success(request, 'Contato remoto salvo no CRM.')
        return redirect(self.build_url_with_query('hubspot_integration:people', 'load=1'))


class HubSpotBulkRemoteContactImportView(HubSpotAccessMixin, View):
    def post(self, request, *args, **kwargs):
        remote_contacts = HubSpotContactService.list_remote_contacts(organization=self.active_organization)
        choices = [(contact['hubspot_contact_id'], contact['email'] or contact['first_name'] or contact['hubspot_contact_id']) for contact in remote_contacts]
        form = HubSpotBulkRemoteContactImportForm(request.POST, contact_choices=choices)
        if not form.is_valid():
            messages.error(request, form.errors.get('hubspot_contact_ids', ['Selecione contatos remotos válidos.'])[0])
            return redirect(self.build_url_with_query('hubspot_integration:people', 'load=1'))

        selected_ids = set(form.cleaned_data['hubspot_contact_ids'])
        selected_contacts = [
            contact
            for contact in remote_contacts
            if contact['hubspot_contact_id'] in selected_ids
        ]
        try:
            HubSpotContactService.import_remote_contacts(
                user=request.user,
                organization=self.active_organization,
                remote_contacts=selected_contacts,
            )
        except (PermissionDenied, ValidationError, Exception) as exc:
            messages.error(request, str(exc))
            return redirect(self.build_url_with_query('hubspot_integration:people', 'load=1'))
        messages.success(request, f'{len(selected_contacts)} contatos remotos foram salvos no CRM.')
        return redirect(self.build_url_with_query('hubspot_integration:people', 'load=1'))


class HubSpotContactCompanySyncView(HubSpotAccessMixin, View):
    def post(self, request, *args, **kwargs):
        form = HubSpotContactCompanySyncForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Não foi possível sincronizar as empresas dos contatos.')
            return redirect(self.build_url_with_query('hubspot_integration:people', 'load=1'))

        try:
            updated_persons = HubSpotContactService.sync_contact_company_links(
                user=request.user,
                organization=self.active_organization,
            )
        except (PermissionDenied, ValidationError, Exception) as exc:
            messages.error(request, str(exc))
            return redirect(self.build_url_with_query('hubspot_integration:people', 'load=1'))

        if updated_persons:
            messages.success(request, f'{len(updated_persons)} pessoas tiveram a empresa sincronizada a partir do HubSpot.')
        else:
            messages.info(request, 'Nenhum vínculo de empresa precisou ser atualizado.')
        return redirect(self.build_url_with_query('hubspot_integration:people', 'load=1'))


class HubSpotPipelinesView(HubSpotAccessMixin):
    template_name = 'hubspot_integration/pipelines.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.build_base_context(active_tab='pipelines'))
        context.update(
            {
                'pipelines': HubSpotPipelineRepository.list_for_organization(self.active_organization),
                'refresh_form': HubSpotPipelineRefreshForm(),
            }
        )
        return context


class HubSpotPipelineRefreshView(HubSpotAccessMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            refreshed_pipelines = HubSpotPipelineService.refresh_pipelines(
                user=request.user,
                organization=self.active_organization,
            )
        except (PermissionDenied, ValidationError, Exception) as exc:
            messages.error(request, str(exc))
            return redirect('hubspot_integration:pipelines')
        messages.success(request, f'{len(refreshed_pipelines)} pipelines do HubSpot foram atualizados.')
        return redirect('hubspot_integration:pipelines')


class HubSpotDealsView(HubSpotAccessMixin):
    template_name = 'hubspot_integration/deals.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            remote_deals = HubSpotDealService.list_remote_deals(organization=self.active_organization)
        except Exception as exc:
            messages.error(self.request, str(exc))
            remote_deals = []
        context.update(self.build_base_context(active_tab='deals'))
        context.update(
            {
                'deals': HubSpotDealRepository.list_for_organization(self.active_organization),
                'remote_deals': remote_deals,
                'deal_form': kwargs.get('deal_form') or HubSpotDealCreateForm(
                    company_choices=self.build_synced_company_choices(),
                    pipeline_choices=self.build_pipeline_choices(),
                    stage_choices=self.build_stage_choices(),
                ),
            }
        )
        return context


class HubSpotDealCreateView(HubSpotAccessMixin, View):
    def post(self, request, *args, **kwargs):
        form = HubSpotDealCreateForm(
            request.POST,
            company_choices=self.build_synced_company_choices(),
            pipeline_choices=self.build_pipeline_choices(),
            stage_choices=self.build_stage_choices(),
        )
        if not form.is_valid():
            view = HubSpotDealsView()
            view.request = request
            view.installation = self.installation
            view.active_organization = self.active_organization
            view.active_membership = self.active_membership
            return view.render_to_response(view.get_context_data(deal_form=form))

        company = CompanyRepository.get_for_organization_and_public_id(
            self.active_organization,
            form.cleaned_data['company_public_id'],
        )
        pipeline = HubSpotPipelineRepository.get_for_organization_and_public_id(
            self.active_organization,
            form.cleaned_data['pipeline_public_id'],
        )
        if company is None or pipeline is None:
            messages.error(request, 'Empresa ou pipeline inválido.')
            return redirect('hubspot_integration:deals')
        try:
            HubSpotDealService.create_deal(
                user=request.user,
                organization=self.active_organization,
                company=company,
                pipeline=pipeline,
                deal_name=form.cleaned_data['deal_name'],
                stage_id=form.cleaned_data['stage_id'],
                amount=form.cleaned_data['amount'],
            )
        except (PermissionDenied, ValidationError, Exception) as exc:
            messages.error(request, str(exc))
            return redirect('hubspot_integration:deals')
        messages.success(request, 'Negocio criado com sucesso no HubSpot.')
        return redirect('hubspot_integration:deals')


class HubSpotDealSearchView(HubSpotAccessMixin, View):
    def get(self, request, *args, **kwargs):
        if not self.active_membership.can_manage_integrations:
            raise PermissionDenied('Somente proprietarios e administradores podem pesquisar negocios do HubSpot.')
        query = (request.GET.get('q') or '').strip()
        return JsonResponse(
            {
                'results': HubSpotDealService.build_deal_option_rows(
                    organization=self.active_organization,
                    query=query,
                )
            }
        )
