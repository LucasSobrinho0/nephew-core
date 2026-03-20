from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.generic import TemplateView

from bot_conversa.exceptions import BotConversaApiError, BotConversaConfigurationError
from hubspot_integration.exceptions import HubSpotApiError, HubSpotConfigurationError
from bot_conversa.forms import (
    BotConversaBulkPersonSyncForm,
    BotConversaPersonCreateForm,
    BotConversaBulkRemoteContactSaveForm,
    BotConversaDispatchCreateForm,
    BotConversaFlowRefreshForm,
    BotConversaListForm,
    BotConversaPersonTagAssignForm,
    BotConversaPersonSyncForm,
    BotConversaRemoteContactSearchForm,
    BotConversaRemoteContactSaveForm,
    BotConversaTagRefreshForm,
)
from bot_conversa.repositories import (
    BotConversaFlowCacheRepository,
    BotConversaFlowDispatchItemRepository,
    BotConversaFlowDispatchRepository,
    BotConversaTagRepository,
)
from bot_conversa.services import (
    BotConversaAuthorizationService,
    BotConversaContactSyncService,
    BotConversaDashboardService,
    BotConversaDispatchService,
    BotConversaDispatchWorkspaceService,
    BotConversaFlowService,
    BotConversaInstallationService,
    BotConversaPeopleService,
    BotConversaRemoteContactService,
    BotConversaTagPreflightService,
    BotConversaTagService,
)
from dispatch_flow.services import DispatchFlowAccessService, DispatchFlowActionService, DispatchFlowWorkspaceService
from people.repositories import PersonRepository


class BotConversaAccessMixin(LoginRequiredMixin):
    missing_organization_message = 'Escolha ou crie uma organização antes de acessar o Bot Conversa.'
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
            self.installation = BotConversaInstallationService.get_installation(
                organization=active_organization,
            )
        except (BotConversaConfigurationError, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect(self.missing_installation_redirect_url)

        request.bot_conversa_installation = self.installation
        self.active_organization = active_organization
        self.active_membership = active_membership
        return None

    def dispatch(self, request, *args, **kwargs):
        redirect_response = self.prepare_request_context(request)
        if redirect_response is not None:
            return redirect_response

        return super().dispatch(request, *args, **kwargs)

    def get_module_tabs(self):
        return [
            {'label': 'Visao geral', 'url': 'bot_conversa:dashboard', 'key': 'dashboard'},
            {'label': 'Pessoas', 'url': 'bot_conversa:people', 'key': 'people'},
            {'label': 'Contatos', 'url': 'bot_conversa:contacts', 'key': 'contacts'},
            {'label': 'Etiquetas', 'url': 'bot_conversa:tags', 'key': 'tags'},
            {'label': 'Fluxos', 'url': 'bot_conversa:flows', 'key': 'flows'},
            {'label': 'Disparos', 'url': 'bot_conversa:dispatches', 'key': 'dispatches'},
        ]

    def build_person_choices(self, *, only_unsent=False, tag_public_ids=None):
        return BotConversaDispatchWorkspaceService.build_person_choices(
            organization=self.active_organization,
            only_unsent=only_unsent,
            tag_public_ids=tag_public_ids,
        )

    def build_flow_choices(self):
        return BotConversaDispatchWorkspaceService.build_flow_choices(
            organization=self.active_organization,
        )

    def build_tag_choices(self):
        return BotConversaDispatchWorkspaceService.build_tag_choices(
            organization=self.active_organization,
        )

    def build_person_create_form(self, *args, **kwargs):
        return BotConversaPersonCreateForm(
            *args,
            tag_choices=self.build_tag_choices(),
            **kwargs,
        )

    def build_dispatch_form(self, *args, **kwargs):
        selected_tag_public_ids = kwargs.pop('selected_tag_public_ids', None)
        data = kwargs.get('data')
        hubspot_enabled = DispatchFlowAccessService.is_app_installed(
            organization=self.active_organization,
            app_code=DispatchFlowAccessService.HUBSPOT_CODE,
        )
        hubspot_preflight_state = {
            'company_choices': [],
            'person_choices': [],
            'deal_person_choices': [],
            'pipeline_choices': [],
            'stage_choices': [],
            'default_target_type': '',
            'default_company_public_id': '',
            'default_person_public_id': '',
            'default_deal_person_public_ids': [],
            'company_contact_warning': '',
            'allow_manual_company_contacts': False,
        }
        if hubspot_enabled and data is not None:
            selected_people = list(
                PersonRepository.list_for_organization_and_public_ids(
                    self.active_organization,
                    data.getlist('person_public_ids') if hasattr(data, 'getlist') else data.get('person_public_ids', []),
                )
            )
            hubspot_preflight_state = DispatchFlowWorkspaceService.build_hubspot_preflight_state(
                organization=self.active_organization,
                selected_people=selected_people,
                data=data,
            )
        return BotConversaDispatchWorkspaceService.build_dispatch_form(
            *args,
            organization=self.active_organization,
            selected_tag_public_ids=selected_tag_public_ids,
            hubspot_enabled=hubspot_enabled,
            hubspot_company_choices=hubspot_preflight_state['company_choices'],
            hubspot_person_choices=hubspot_preflight_state['person_choices'],
            hubspot_deal_person_choices=hubspot_preflight_state['deal_person_choices'],
            hubspot_pipeline_choices=hubspot_preflight_state['pipeline_choices'],
            hubspot_stage_choices=hubspot_preflight_state['stage_choices'],
            hubspot_default_target_type=hubspot_preflight_state['default_target_type'],
            hubspot_default_company_public_id=hubspot_preflight_state['default_company_public_id'],
            hubspot_default_person_public_id=hubspot_preflight_state['default_person_public_id'],
            hubspot_default_deal_person_public_ids=hubspot_preflight_state['default_deal_person_public_ids'],
            hubspot_company_contact_warning=hubspot_preflight_state['company_contact_warning'],
            hubspot_allow_manual_company_contacts=hubspot_preflight_state['allow_manual_company_contacts'],
            **kwargs,
        )

    def build_base_context(self, *, active_tab):
        return {
            'bot_conversa_installation': self.installation,
            'bot_conversa_tabs': self.get_module_tabs(),
            'bot_conversa_active_tab': active_tab,
            'can_manage_bot_conversa': self.active_membership.can_manage_integrations,
        }


class BotConversaOperatorRequiredMixin(BotConversaAccessMixin):
    def dispatch(self, request, *args, **kwargs):
        redirect_response = self.prepare_request_context(request)
        if redirect_response is not None:
            return redirect_response

        if not self.active_membership.can_manage_integrations:
            messages.error(request, 'Somente proprietarios e administradores podem operar acoes do Bot Conversa.')
            return redirect('bot_conversa:dashboard')

        return super(BotConversaAccessMixin, self).dispatch(request, *args, **kwargs)


class BotConversaDashboardView(BotConversaAccessMixin, TemplateView):
    template_name = 'bot_conversa/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.build_base_context(active_tab='dashboard'))
        context['summary'] = BotConversaDashboardService.build_summary(
            organization=self.active_organization,
        )
        return context


class BotConversaPeopleView(BotConversaAccessMixin, TemplateView):
    template_name = 'bot_conversa/people.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        list_form = BotConversaListForm(self.request.GET or None)
        has_loaded_people = kwargs.get('force_load_people', False)
        person_rows = []

        if has_loaded_people or (self.request.GET.get('load') == '1' and list_form.is_valid()):
            has_loaded_people = True
            person_rows = BotConversaPeopleService.build_person_rows(
                organization=self.active_organization,
            )

        context.update(self.build_base_context(active_tab='people'))
        context.update(
            {
                'person_rows': person_rows,
                'has_loaded_people': has_loaded_people,
                'list_form': list_form,
                'create_form': kwargs.get('create_form') or self.build_person_create_form(),
                'bulk_sync_form': kwargs.get('bulk_sync_form') or BotConversaBulkPersonSyncForm(
                    person_choices=self.build_person_choices(),
                    tag_choices=self.build_tag_choices(),
                    form_id='botBulkPersonSyncForm',
                    initial={'next': 'bot_conversa:people'},
                ),
                'selected_sync_person_public_ids': kwargs.get('selected_sync_person_public_ids', []),
                'sync_tag_preflight_modal_open': kwargs.get('sync_tag_preflight_modal_open', False),
                'sync_tag_preflight_people': kwargs.get('sync_tag_preflight_people', []),
            }
        )
        return context


class BotConversaPersonCreateView(BotConversaOperatorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = self.build_person_create_form(request.POST)
        if not form.is_valid():
            view = BotConversaPeopleView()
            view.request = request
            view.args = args
            view.kwargs = kwargs
            view.installation = self.installation
            view.active_organization = self.active_organization
            view.active_membership = self.active_membership
            return view.render_to_response(
                view.get_context_data(create_form=form),
            )

        try:
            tags = list(
                BotConversaTagRepository.list_for_organization_and_public_ids(
                    self.active_organization,
                    form.cleaned_data['tag_public_ids'],
                )
            )
            BotConversaPeopleService.create_person_with_tags(
                user=request.user,
                organization=self.active_organization,
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
                phone=form.cleaned_data['phone'],
                email=form.cleaned_data['email'],
                tags=tags,
            )
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect('bot_conversa:people')

        if form.cleaned_data['tag_public_ids']:
            messages.success(request, 'Pessoa criada com sucesso e vinculada as etiquetas selecionadas.')
        else:
            messages.success(request, 'Pessoa criada com sucesso.')
        return redirect('bot_conversa:people')


class BotConversaPersonSyncView(BotConversaOperatorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = BotConversaPersonSyncForm(request.POST)
        next_url = request.POST.get('next') or 'bot_conversa:people'

        if not form.is_valid():
            messages.error(request, 'Selecione uma pessoa valida para sincronizar.')
            return redirect(next_url)

        person = PersonRepository.get_for_organization_and_public_id(
            self.active_organization,
            form.cleaned_data['person_public_id'],
        )
        if person is None:
            messages.error(request, 'A pessoa selecionada nao foi encontrada.')
            return redirect(next_url)

        try:
            BotConversaContactSyncService.sync_person(
                user=request.user,
                organization=self.active_organization,
                person=person,
            )
        except (BotConversaApiError, BotConversaConfigurationError, PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect(next_url)

        messages.success(request, f'{person.full_name} agora esta vinculado ao Bot Conversa.')
        return redirect(next_url)


class BotConversaBulkPersonSyncView(BotConversaOperatorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        post_data = request.POST.copy()
        modal_submit_action = post_data.get('tag_preflight_modal_submit')
        if modal_submit_action in {'skip', 'apply'}:
            post_data['skip_tag_preflight'] = '1'
            post_data['tag_preflight_action'] = 'apply' if modal_submit_action == 'apply' else ''

        form = BotConversaBulkPersonSyncForm(
            post_data,
            person_choices=self.build_person_choices(),
            tag_choices=self.build_tag_choices(),
            form_id='botBulkPersonSyncForm',
        )
        next_url = post_data.get('next') or 'bot_conversa:people'

        if not form.is_valid():
            messages.error(request, form.errors.get('person_public_ids', ['Selecione pessoas válidas.'])[0])
            return redirect(next_url)

        persons = list(
            PersonRepository.list_for_organization_and_public_ids(
                self.active_organization,
                form.cleaned_data['person_public_ids'],
            )
        )

        if not form.cleaned_data['skip_tag_preflight']:
            untagged_people = BotConversaTagPreflightService.list_untagged_people(
                organization=self.active_organization,
                persons=persons,
            )
            if untagged_people:
                view = BotConversaPeopleView()
                view.request = request
                view.args = args
                view.kwargs = kwargs
                view.installation = self.installation
                view.active_organization = self.active_organization
                view.active_membership = self.active_membership
                return view.render_to_response(
                    view.get_context_data(
                        bulk_sync_form=form,
                        force_load_people=True,
                        selected_sync_person_public_ids=form.cleaned_data['person_public_ids'],
                        sync_tag_preflight_modal_open=True,
                        sync_tag_preflight_people=untagged_people,
                    ),
                )

        try:
            if form.cleaned_data['tag_preflight_action'] == 'apply' and not form.cleaned_data['tag_public_ids']:
                view = BotConversaPeopleView()
                view.request = request
                view.args = args
                view.kwargs = kwargs
                view.installation = self.installation
                view.active_organization = self.active_organization
                view.active_membership = self.active_membership
                form.add_error('tag_public_ids', 'Selecione pelo menos uma etiqueta para continuar.')
                return view.render_to_response(
                    view.get_context_data(
                        bulk_sync_form=form,
                        force_load_people=True,
                        selected_sync_person_public_ids=form.cleaned_data['person_public_ids'],
                        sync_tag_preflight_modal_open=True,
                        sync_tag_preflight_people=BotConversaTagPreflightService.list_untagged_people(
                            organization=self.active_organization,
                            persons=persons,
                        ),
                    ),
                )
            if form.cleaned_data['tag_public_ids']:
                BotConversaTagPreflightService.apply_tags_by_public_ids(
                    user=request.user,
                    organization=self.active_organization,
                    persons=persons,
                    tag_public_ids=form.cleaned_data['tag_public_ids'],
                )
            BotConversaContactSyncService.sync_people(
                user=request.user,
                organization=self.active_organization,
                persons=persons,
            )
        except (BotConversaApiError, BotConversaConfigurationError, PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect(next_url)

        messages.success(request, f'{len(persons)} pessoas foram sincronizadas com o Bot Conversa.')
        return redirect(next_url)


class BotConversaContactsView(BotConversaAccessMixin, TemplateView):
    template_name = 'bot_conversa/contacts.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_form = BotConversaRemoteContactSearchForm(self.request.GET or None)
        remote_contacts = []

        if search_form.is_valid():
            try:
                remote_contacts = BotConversaRemoteContactService.list_contacts(
                    organization=self.active_organization,
                    search=search_form.cleaned_data['search'],
                )
            except (BotConversaApiError, BotConversaConfigurationError) as exc:
                messages.error(self.request, str(exc))

        context.update(self.build_base_context(active_tab='contacts'))
        context.update(
            {
                'search_form': search_form,
                'remote_contacts': remote_contacts,
                'local_contacts': BotConversaPeopleService.build_person_rows(
                    organization=self.active_organization,
                ),
            }
        )
        return context


class BotConversaRemoteContactSaveView(BotConversaOperatorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = BotConversaRemoteContactSaveForm(request.POST)
        next_url = request.POST.get('next') or 'bot_conversa:contacts'

        if not form.is_valid():
            messages.error(request, 'Os dados do contato remoto sao invalidos para salvar no CRM.')
            return redirect(next_url)

        try:
            save_result = BotConversaRemoteContactService.save_contact_to_crm(
                user=request.user,
                organization=self.active_organization,
                external_subscriber_id=form.cleaned_data['external_subscriber_id'],
                phone=form.cleaned_data['phone'],
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
                external_name=form.cleaned_data['external_name'],
            )
        except (BotConversaApiError, BotConversaConfigurationError, PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect(next_url)

        person = save_result['person']
        if save_result['created_person']:
            messages.success(request, f'{person.full_name} foi salvo no CRM com sucesso.')
        elif save_result['linked_existing_person']:
            messages.success(request, f'{person.full_name} foi atualizado com o ID do Bot Conversa.')
        else:
            messages.info(request, f'{person.full_name} ja estava salvo no CRM.')

        return redirect(next_url)


class BotConversaBulkRemoteContactSaveView(BotConversaOperatorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        search_form = BotConversaRemoteContactSearchForm(request.GET or None)
        current_search = request.POST.get('current_search', '')
        remote_contacts = BotConversaRemoteContactService.list_contacts(
            organization=self.active_organization,
            search=current_search,
        )
        choices = [
            (contact['external_subscriber_id'], contact['name'] or contact['external_subscriber_id'])
            for contact in remote_contacts
        ]
        form = BotConversaBulkRemoteContactSaveForm(request.POST, subscriber_choices=choices)
        next_url = request.POST.get('next') or 'bot_conversa:contacts'

        if not form.is_valid():
            messages.error(request, form.errors.get('external_subscriber_ids', ['Selecione contatos remotos válidos.'])[0])
            return redirect(next_url)

        selected_ids = set(form.cleaned_data['external_subscriber_ids'])
        selected_contacts = [
            contact
            for contact in remote_contacts
            if contact['external_subscriber_id'] in selected_ids
        ]
        try:
            saved_persons = BotConversaRemoteContactService.save_contacts_to_crm(
                user=request.user,
                organization=self.active_organization,
                remote_contacts=selected_contacts,
            )
        except (BotConversaApiError, BotConversaConfigurationError, PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect(next_url)

        messages.success(request, f'{len(saved_persons)} contatos remotos foram salvos no CRM.')
        return redirect(next_url)


class BotConversaFlowsView(BotConversaAccessMixin, TemplateView):
    template_name = 'bot_conversa/flows.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.build_base_context(active_tab='flows'))
        context.update(
            {
                'flows': BotConversaFlowCacheRepository.list_for_organization(self.active_organization),
                'refresh_form': BotConversaFlowRefreshForm(),
            }
        )
        return context


class BotConversaFlowRefreshView(BotConversaOperatorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = BotConversaFlowRefreshForm(request.POST)
        next_url = request.POST.get('next') or 'bot_conversa:flows'

        if not form.is_valid():
            messages.error(request, 'A solicitacao de atualizacao de fluxos e invalida.')
            return redirect(next_url)

        try:
            refreshed_flows = BotConversaFlowService.refresh_flows(
                user=request.user,
                organization=self.active_organization,
            )
        except (BotConversaApiError, BotConversaConfigurationError, PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect(next_url)

        messages.success(request, f'{len(refreshed_flows)} fluxos do Bot Conversa foram atualizados com sucesso.')
        return redirect(next_url)


class BotConversaDispatchesView(BotConversaAccessMixin, TemplateView):
    template_name = 'bot_conversa/dispatches.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_tag_public_ids = kwargs.get('selected_tag_public_ids') or self.request.GET.getlist('tag_public_ids')
        context.update(self.build_base_context(active_tab='dispatches'))
        context.update(
            {
                'dispatch_form': kwargs.get('dispatch_form')
                or self.build_dispatch_form(
                    initial={'tag_public_ids': selected_tag_public_ids},
                    selected_tag_public_ids=selected_tag_public_ids,
                ),
                'bot_dispatch_action_url': reverse('bot_conversa:create_dispatch'),
                'recent_dispatches': BotConversaFlowDispatchRepository.list_recent_for_organization(
                    self.active_organization,
                ),
                'initial_bot_conversa_audience_count': len(
                    self.build_person_choices(tag_public_ids=selected_tag_public_ids)
                ),
                'hubspot_enabled': DispatchFlowAccessService.is_app_installed(
                    organization=self.active_organization,
                    app_code=DispatchFlowAccessService.HUBSPOT_CODE,
                ),
                'hubspot_preflight_modal_open': kwargs.get('hubspot_preflight_modal_open', False),
                'hubspot_preflight_people': kwargs.get('hubspot_preflight_people', []),
                'hubspot_preflight_modal_errors': kwargs.get('hubspot_preflight_modal_errors', []),
                'dispatch_tag_preflight_modal_open': kwargs.get('dispatch_tag_preflight_modal_open', False),
                'dispatch_tag_preflight_people': kwargs.get('dispatch_tag_preflight_people', []),
                'dispatch_tag_preflight_modal_errors': kwargs.get('dispatch_tag_preflight_modal_errors', []),
            }
        )
        return context


class BotConversaTagsView(BotConversaAccessMixin, TemplateView):
    template_name = 'bot_conversa/tags.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        list_form = BotConversaListForm(self.request.GET or None)
        has_loaded_people = False
        person_rows = []

        if self.request.GET.get('load') == '1' and list_form.is_valid():
            has_loaded_people = True
            person_rows = BotConversaPeopleService.build_person_rows(
                organization=self.active_organization,
            )

        context.update(self.build_base_context(active_tab='tags'))
        context.update(
            {
                'tag_rows': BotConversaTagService.build_tag_rows(organization=self.active_organization),
                'refresh_form': BotConversaTagRefreshForm(),
                'assign_form': kwargs.get('assign_form') or BotConversaPersonTagAssignForm(
                    tag_choices=self.build_tag_choices(),
                    person_choices=self.build_person_choices(),
                    initial={'next': 'bot_conversa:tags'},
                ),
                'person_rows': person_rows,
                'has_loaded_people': has_loaded_people,
                'list_form': list_form,
            }
        )
        return context


class BotConversaTagRefreshView(BotConversaOperatorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = BotConversaTagRefreshForm(request.POST)
        next_url = request.POST.get('next') or 'bot_conversa:tags'

        if not form.is_valid():
            messages.error(request, 'A solicitacao de atualizacao de etiquetas e invalida.')
            return redirect(next_url)

        try:
            refreshed_tags = BotConversaTagService.refresh_tags(
                user=request.user,
                organization=self.active_organization,
            )
        except (BotConversaApiError, BotConversaConfigurationError, PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect(next_url)

        messages.success(request, f'{len(refreshed_tags)} etiquetas do Bot Conversa foram atualizadas.')
        return redirect(next_url)


class BotConversaTagAssignView(BotConversaOperatorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = BotConversaPersonTagAssignForm(
            request.POST,
            tag_choices=self.build_tag_choices(),
            person_choices=self.build_person_choices(),
        )
        next_url = request.POST.get('next') or 'bot_conversa:tags'

        if not form.is_valid():
            view = BotConversaTagsView()
            view.request = request
            view.args = args
            view.kwargs = kwargs
            view.installation = self.installation
            view.active_organization = self.active_organization
            view.active_membership = self.active_membership
            return view.render_to_response(view.get_context_data(assign_form=form))

        tag = BotConversaTagRepository.get_for_organization_and_public_id(
            self.active_organization,
            form.cleaned_data['tag_public_id'],
        )
        if tag is None:
            messages.error(request, 'Selecione uma etiqueta valida do Bot Conversa.')
            return redirect(next_url)

        persons = list(
            PersonRepository.list_for_organization_and_public_ids(
                self.active_organization,
                form.cleaned_data['person_public_ids'],
            )
        )
        try:
            linked_persons = BotConversaTagService.assign_tag_to_people(
                user=request.user,
                organization=self.active_organization,
                tag=tag,
                persons=persons,
            )
        except (BotConversaApiError, BotConversaConfigurationError, PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect(next_url)

        messages.success(request, f'{len(linked_persons)} pessoas foram vinculadas a etiqueta {tag.name}.')
        return redirect(next_url)


class BotConversaDispatchCreateView(BotConversaOperatorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        post_data = request.POST.copy()
        modal_submit_action = post_data.get('tag_preflight_modal_submit')
        if modal_submit_action in {'skip', 'apply'}:
            post_data['skip_tag_preflight'] = '1'
            post_data['tag_preflight_action'] = 'apply' if modal_submit_action == 'apply' else ''
        hubspot_modal_submit = post_data.get('hubspot_preflight_modal_submit')
        if hubspot_modal_submit in {'skip', 'apply'}:
            post_data['skip_hubspot_preflight'] = '1'
            post_data['hubspot_preflight_action'] = hubspot_modal_submit

        form = self.build_dispatch_form(data=post_data)
        if not form.is_valid():
            view = BotConversaDispatchesView()
            view.request = request
            view.args = args
            view.kwargs = kwargs
            view.installation = self.installation
            view.active_organization = self.active_organization
            view.active_membership = self.active_membership
            return view.render_to_response(
                view.get_context_data(
                    dispatch_form=form,
                    selected_tag_public_ids=post_data.getlist('tag_public_ids'),
                ),
            )

        flow_cache = BotConversaFlowCacheRepository.get_for_organization_and_public_id(
            self.active_organization,
            form.cleaned_data['flow_public_id'],
        )
        if flow_cache is None:
            messages.error(request, 'Selecione um fluxo valido do Bot Conversa.')
            return redirect('bot_conversa:dispatches')

        persons = list(
            PersonRepository.list_for_organization_and_public_ids(
                self.active_organization,
                form.cleaned_data['person_public_ids'],
            )
        )
        tags = list(
            BotConversaTagRepository.list_for_organization_and_public_ids(
                self.active_organization,
                form.cleaned_data['tag_public_ids'],
            )
        )

        if not form.cleaned_data['skip_tag_preflight']:
            untagged_people = BotConversaTagPreflightService.list_untagged_people(
                organization=self.active_organization,
                persons=persons,
            )
            if untagged_people:
                view = BotConversaDispatchesView()
                view.request = request
                view.args = args
                view.kwargs = kwargs
                view.installation = self.installation
                view.active_organization = self.active_organization
                view.active_membership = self.active_membership
                return view.render_to_response(
                    view.get_context_data(
                        dispatch_form=form,
                        selected_tag_public_ids=post_data.getlist('tag_public_ids'),
                        dispatch_tag_preflight_modal_open=True,
                        dispatch_tag_preflight_people=untagged_people,
                    ),
                )

        try:
            if form.cleaned_data['tag_preflight_action'] == 'apply' and not form.cleaned_data['preflight_tag_public_ids']:
                view = BotConversaDispatchesView()
                view.request = request
                view.args = args
                view.kwargs = kwargs
                view.installation = self.installation
                view.active_organization = self.active_organization
                view.active_membership = self.active_membership
                form.add_error('preflight_tag_public_ids', 'Selecione pelo menos uma etiqueta para continuar.')
                return view.render_to_response(
                    view.get_context_data(
                        dispatch_form=form,
                        selected_tag_public_ids=post_data.getlist('tag_public_ids'),
                        dispatch_tag_preflight_modal_open=True,
                        dispatch_tag_preflight_people=BotConversaTagPreflightService.list_untagged_people(
                            organization=self.active_organization,
                            persons=persons,
                        ),
                    ),
                )

            if form.cleaned_data['tag_preflight_action'] == 'apply' and form.cleaned_data['preflight_tag_public_ids']:
                BotConversaTagPreflightService.apply_tags_by_public_ids(
                    user=request.user,
                    organization=self.active_organization,
                    persons=persons,
                    tag_public_ids=form.cleaned_data['preflight_tag_public_ids'],
                )

            if (
                DispatchFlowAccessService.is_app_installed(
                    organization=self.active_organization,
                    app_code=DispatchFlowAccessService.HUBSPOT_CODE,
                )
                and not form.cleaned_data['skip_hubspot_preflight']
            ):
                hubspot_preflight = DispatchFlowActionService.build_hubspot_preflight(
                    organization=self.active_organization,
                    persons=persons,
                )
                if hubspot_preflight['should_prompt']:
                    view = BotConversaDispatchesView()
                    view.request = request
                    view.args = args
                    view.kwargs = kwargs
                    view.installation = self.installation
                    view.active_organization = self.active_organization
                    view.active_membership = self.active_membership
                    return view.render_to_response(
                        view.get_context_data(
                            dispatch_form=form,
                            selected_tag_public_ids=post_data.getlist('tag_public_ids'),
                            hubspot_preflight_modal_open=True,
                            hubspot_preflight_people=hubspot_preflight['selected_people'],
                        ),
                    )

            DispatchFlowActionService.apply_hubspot_actions_if_requested(
                user=request.user,
                organization=self.active_organization,
                persons=persons,
                preflight_action=form.cleaned_data['hubspot_preflight_action'],
                create_deal_now=form.cleaned_data['hubspot_create_deal_now'],
                target_type=form.cleaned_data['hubspot_deal_target_type'],
                target_company_public_id=form.cleaned_data['hubspot_target_company_public_id'],
                target_person_public_id=form.cleaned_data['hubspot_target_person_public_id'],
                deal_person_public_ids=form.cleaned_data['hubspot_deal_person_public_ids'],
                pipeline_public_id=form.cleaned_data['hubspot_pipeline_public_id'],
                stage_id=form.cleaned_data['hubspot_stage_id'],
            )

            dispatch = BotConversaDispatchService.create_dispatch(
                user=request.user,
                organization=self.active_organization,
                flow_cache=flow_cache,
                persons=persons,
                tags=tags,
                min_delay_seconds=form.cleaned_data['min_delay_seconds'],
                max_delay_seconds=form.cleaned_data['max_delay_seconds'],
            )
        except (PermissionDenied, ValidationError, HubSpotApiError, HubSpotConfigurationError) as exc:
            view = BotConversaDispatchesView()
            view.request = request
            view.args = args
            view.kwargs = kwargs
            view.installation = self.installation
            view.active_organization = self.active_organization
            view.active_membership = self.active_membership
            return view.render_to_response(
                view.get_context_data(
                    dispatch_form=form,
                    selected_tag_public_ids=post_data.getlist('tag_public_ids'),
                    dispatch_tag_preflight_modal_open=bool(form.cleaned_data.get('person_public_ids')),
                    dispatch_tag_preflight_people=BotConversaTagPreflightService.list_untagged_people(
                        organization=self.active_organization,
                        persons=persons,
                    ),
                    dispatch_tag_preflight_modal_errors=[str(exc)],
                    hubspot_preflight_modal_open=post_data.get('hubspot_preflight_modal_submit') in {'apply', 'skip'},
                    hubspot_preflight_people=persons,
                    hubspot_preflight_modal_errors=[str(exc)] if 'HubSpot' in str(exc) or 'hubspot' in str(exc).lower() else [],
                ),
            )

        messages.success(request, 'Disparo do fluxo criado. O processamento continuara na tela de status.')
        return redirect('bot_conversa:dispatch_detail', dispatch_public_id=dispatch.public_id)


class BotConversaDispatchDetailView(BotConversaAccessMixin, TemplateView):
    template_name = 'bot_conversa/dispatch_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dispatch = BotConversaFlowDispatchRepository.get_for_organization_and_public_id(
            self.active_organization,
            self.kwargs['dispatch_public_id'],
        )
        if dispatch is None:
            raise Http404('Disparo nao encontrado.')

        context.update(self.build_base_context(active_tab='dispatches'))
        context.update(BotConversaDispatchService.build_dispatch_payload(dispatch=dispatch))
        return context


class BotConversaDispatchPauseView(BotConversaOperatorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        dispatch = BotConversaFlowDispatchRepository.get_for_organization_and_public_id(
            self.active_organization,
            kwargs['dispatch_public_id'],
        )
        if dispatch is None:
            raise Http404('Disparo nao encontrado.')

        try:
            BotConversaDispatchService.pause_dispatch(
                user=request.user,
                organization=self.active_organization,
                dispatch=dispatch,
            )
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect('bot_conversa:dispatch_detail', dispatch_public_id=dispatch.public_id)

        messages.success(request, 'Envio pausado.')
        return redirect('bot_conversa:dispatch_detail', dispatch_public_id=dispatch.public_id)


class BotConversaDispatchResumeView(BotConversaOperatorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        dispatch = BotConversaFlowDispatchRepository.get_for_organization_and_public_id(
            self.active_organization,
            kwargs['dispatch_public_id'],
        )
        if dispatch is None:
            raise Http404('Disparo nao encontrado.')

        try:
            BotConversaDispatchService.resume_dispatch(
                user=request.user,
                organization=self.active_organization,
                dispatch=dispatch,
            )
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect('bot_conversa:dispatch_detail', dispatch_public_id=dispatch.public_id)

        messages.success(request, 'Envio retomado.')
        return redirect('bot_conversa:dispatch_detail', dispatch_public_id=dispatch.public_id)


class BotConversaDispatchReprocessRunningView(BotConversaOperatorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        dispatch = BotConversaFlowDispatchRepository.get_for_organization_and_public_id(
            self.active_organization,
            kwargs['dispatch_public_id'],
        )
        if dispatch is None:
            raise Http404('Disparo nao encontrado.')

        try:
            requeued_count = BotConversaDispatchService.reprocess_running_items(
                user=request.user,
                organization=self.active_organization,
                dispatch=dispatch,
            )
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect('bot_conversa:dispatch_detail', dispatch_public_id=dispatch.public_id)

        messages.success(request, f'{requeued_count} item(ns) travado(s) foram recolocados na fila.')
        return redirect('bot_conversa:dispatch_detail', dispatch_public_id=dispatch.public_id)


@method_decorator(never_cache, name='dispatch')
class BotConversaDispatchAudienceView(BotConversaAccessMixin, View):
    http_method_names = ['get']

    def get(self, request, *args, **kwargs):
        only_unsent = request.GET.get('only_unsent') == '1'
        tag_public_ids = request.GET.getlist('tag_public_ids')
        person_choices = self.build_person_choices(
            only_unsent=only_unsent,
            tag_public_ids=tag_public_ids,
        )
        response = JsonResponse(
            {
                'items': [
                    {
                        'value': value,
                        'label': label,
                    }
                    for value, label in person_choices
                ],
                'count': len(person_choices),
                'only_unsent': only_unsent,
                'empty_message': (
                    'Nenhuma pessoa sem envio anterior no WhatsApp esta disponivel para este disparo.'
                    if only_unsent
                    else 'Nenhuma pessoa cadastrada no CRM esta disponivel para este disparo.'
                ),
            }
        )
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response


@method_decorator(never_cache, name='dispatch')
class BotConversaDispatchProcessView(LoginRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        active_organization = getattr(request, 'active_organization', None)
        if active_organization is None:
            return self.build_json_response({'detail': 'Nenhuma organização ativa foi encontrada.'}, status=400)

        try:
            BotConversaAuthorizationService.ensure_operator_access(
                user=request.user,
                organization=active_organization,
            )
            BotConversaInstallationService.get_installation(organization=active_organization)
        except PermissionDenied as exc:
            return self.build_json_response({'detail': str(exc)}, status=403)
        except (BotConversaConfigurationError, ValidationError) as exc:
            return self.build_json_response({'detail': str(exc)}, status=400)

        dispatch = BotConversaFlowDispatchRepository.get_for_organization_and_public_id(
            active_organization,
            kwargs['dispatch_public_id'],
        )
        if dispatch is None:
            raise Http404('Disparo nao encontrado.')

        try:
            dispatch = BotConversaDispatchService.process_pending_items(
                user=request.user,
                organization=active_organization,
                dispatch=dispatch,
            )
        except (BotConversaApiError, BotConversaConfigurationError, PermissionDenied, ValidationError) as exc:
            return self.build_json_response({'detail': str(exc)}, status=400)

        return self.build_json_response(
            BotConversaDispatchService.build_dispatch_payload(dispatch=dispatch)['status_payload'],
            status=200,
        )

    @staticmethod
    def build_json_response(payload, *, status):
        response = JsonResponse(payload, status=status)
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
