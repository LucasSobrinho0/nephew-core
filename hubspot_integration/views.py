from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from companies.repositories import CompanyRepository
from hubspot_integration.forms import (
    HubSpotCompanyCreateForm,
    HubSpotCompanySyncForm,
    HubSpotDealCreateForm,
    HubSpotPersonSyncForm,
    HubSpotPipelineRefreshForm,
    HubSpotRemoteCompanyImportForm,
    HubSpotRemoteContactImportForm,
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
        return [
            (str(company.public_id), company.name)
            for company in CompanyRepository.list_for_organization(self.active_organization)
            if company.hubspot_company_id
        ]

    def build_pipeline_choices(self):
        return [
            (str(pipeline.public_id), pipeline.name)
            for pipeline in HubSpotPipelineRepository.list_for_organization(self.active_organization)
        ]

    def build_base_context(self, *, active_tab):
        return {
            'hubspot_tabs': [
                {'label': 'Visão geral', 'url': 'hubspot_integration:dashboard', 'key': 'dashboard'},
                {'label': 'Empresas', 'url': 'hubspot_integration:companies', 'key': 'companies'},
                {'label': 'Pessoas', 'url': 'hubspot_integration:people', 'key': 'people'},
                {'label': 'Pipelines', 'url': 'hubspot_integration:pipelines', 'key': 'pipelines'},
                {'label': 'Deals', 'url': 'hubspot_integration:deals', 'key': 'deals'},
            ],
            'hubspot_active_tab': active_tab,
            'can_manage_hubspot': self.active_membership.can_manage_integrations,
        }


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
        try:
            remote_companies = HubSpotCompanyService.list_remote_companies(organization=self.active_organization)
        except Exception as exc:
            messages.error(self.request, str(exc))
            remote_companies = []
        context.update(self.build_base_context(active_tab='companies'))
        context.update(
            {
                'company_rows': HubSpotCompanyService.build_company_rows(organization=self.active_organization),
                'remote_companies': remote_companies,
                'create_form': kwargs.get('create_form') or HubSpotCompanyCreateForm(),
                'sync_form': HubSpotCompanySyncForm(),
                'remote_import_form': HubSpotRemoteCompanyImportForm(),
            }
        )
        return context


class HubSpotCompanyCreateView(HubSpotAccessMixin, View):
    def post(self, request, *args, **kwargs):
        form = HubSpotCompanyCreateForm(request.POST)
        if not form.is_valid():
            view = HubSpotCompaniesView()
            view.request = request
            view.installation = self.installation
            view.active_organization = self.active_organization
            view.active_membership = self.active_membership
            return view.render_to_response(view.get_context_data(create_form=form))
        try:
            HubSpotCompanyService.create_local_company(
                user=request.user,
                organization=self.active_organization,
                name=form.cleaned_data['name'],
                website=form.cleaned_data['website'],
                phone=form.cleaned_data['phone'],
            )
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect('hubspot_integration:companies')
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
            HubSpotCompanyService.sync_company(
                user=request.user,
                organization=self.active_organization,
                company=company,
            )
        except (PermissionDenied, ValidationError, Exception) as exc:
            messages.error(request, str(exc))
            return redirect('hubspot_integration:companies')
        messages.success(request, 'Empresa sincronizada com o HubSpot.')
        return redirect('hubspot_integration:companies')


class HubSpotRemoteCompanyImportView(HubSpotAccessMixin, View):
    def post(self, request, *args, **kwargs):
        form = HubSpotRemoteCompanyImportForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Os dados da empresa remota são inválidos.')
            return redirect('hubspot_integration:companies')
        try:
            _company, was_created = HubSpotCompanyService.import_remote_company(
                user=request.user,
                organization=self.active_organization,
                hubspot_company_id=form.cleaned_data['hubspot_company_id'],
                name=form.cleaned_data['name'],
                website=form.cleaned_data['website'],
                phone=form.cleaned_data['phone'],
            )
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect('hubspot_integration:companies')
        if was_created:
            messages.success(request, 'Empresa remota salva no CRM.')
        else:
            messages.info(request, 'Essa empresa já está salva no CRM.')
        return redirect('hubspot_integration:companies')


class HubSpotPeopleView(HubSpotAccessMixin):
    template_name = 'hubspot_integration/people.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            remote_contacts = HubSpotContactService.list_remote_contacts(organization=self.active_organization)
        except Exception as exc:
            messages.error(self.request, str(exc))
            remote_contacts = []
        context.update(self.build_base_context(active_tab='people'))
        context.update(
            {
                'person_rows': HubSpotContactService.build_person_rows(organization=self.active_organization),
                'remote_contacts': remote_contacts,
                'sync_form': HubSpotPersonSyncForm(),
            }
        )
        return context


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
            HubSpotContactService.sync_person(
                user=request.user,
                organization=self.active_organization,
                person=person,
            )
        except (PermissionDenied, ValidationError, Exception) as exc:
            messages.error(request, str(exc))
            return redirect('hubspot_integration:people')
        messages.success(request, 'Pessoa sincronizada com o HubSpot.')
        return redirect('hubspot_integration:people')


class HubSpotRemoteContactImportView(HubSpotAccessMixin, View):
    def post(self, request, *args, **kwargs):
        form = HubSpotRemoteContactImportForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Os dados do contato remoto são inválidos.')
            return redirect('hubspot_integration:people')
        try:
            _person, was_created = HubSpotContactService.import_remote_contact(
                user=request.user,
                organization=self.active_organization,
                hubspot_contact_id=form.cleaned_data['hubspot_contact_id'],
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
                email=form.cleaned_data['email'],
                phone=form.cleaned_data['phone'],
                company_name=form.cleaned_data['company_name'],
                company_hubspot_id=form.cleaned_data['company_hubspot_id'],
            )
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect('hubspot_integration:people')
        if was_created:
            messages.success(request, 'Contato remoto salvo no CRM.')
        else:
            messages.info(request, 'Esse contato já está salvo no CRM.')
        return redirect('hubspot_integration:people')


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
        context.update(self.build_base_context(active_tab='deals'))
        context.update(
            {
                'deals': HubSpotDealRepository.list_for_organization(self.active_organization),
                'deal_form': kwargs.get('deal_form') or HubSpotDealCreateForm(
                    company_choices=self.build_company_choices(),
                    pipeline_choices=self.build_pipeline_choices(),
                ),
            }
        )
        return context


class HubSpotDealCreateView(HubSpotAccessMixin, View):
    def post(self, request, *args, **kwargs):
        form = HubSpotDealCreateForm(
            request.POST,
            company_choices=self.build_company_choices(),
            pipeline_choices=self.build_pipeline_choices(),
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
                amount=form.cleaned_data['amount'],
            )
        except (PermissionDenied, ValidationError, Exception) as exc:
            messages.error(request, str(exc))
            return redirect('hubspot_integration:deals')
        messages.success(request, 'Deal criado com sucesso no HubSpot.')
        return redirect('hubspot_integration:deals')
