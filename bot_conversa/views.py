from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.generic import TemplateView

from bot_conversa.exceptions import BotConversaApiError, BotConversaConfigurationError
from bot_conversa.forms import (
    BotConversaBulkPersonSyncForm,
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
    BotConversaFlowService,
    BotConversaInstallationService,
    BotConversaPeopleService,
    BotConversaRemoteContactService,
    BotConversaTagService,
)
from people.forms import PersonCreateForm
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
        persons = list(PersonRepository.list_for_organization(self.active_organization))
        selected_tag_ids = []

        if tag_public_ids:
            selected_tag_ids = [
                tag.id
                for tag in BotConversaTagRepository.list_for_organization_and_public_ids(
                    self.active_organization,
                    tag_public_ids,
                )
            ]

        if selected_tag_ids:
            tagged_person_ids = set(
                BotConversaTagService.list_person_ids_for_tags(
                    organization=self.active_organization,
                    tag_ids=selected_tag_ids,
                )
            )
            persons = [person for person in persons if person.id in tagged_person_ids]

        if only_unsent:
            successful_person_ids = set(
                BotConversaFlowDispatchItemRepository.list_success_person_ids_for_organization(
                    self.active_organization,
                )
            )
            persons = [person for person in persons if person.id not in successful_person_ids]

        return [
            (str(person.public_id), f'{person.full_name} - {person.phone}')
            for person in persons
        ]

    def build_flow_choices(self):
        return [
            (str(flow.public_id), flow.name)
            for flow in BotConversaFlowCacheRepository.list_selectable_for_organization(self.active_organization)
        ]

    def build_tag_choices(self):
        return BotConversaTagService.build_tag_choice_rows(organization=self.active_organization)

    def build_dispatch_form(self, *args, **kwargs):
        person_choices = self.build_person_choices(
            tag_public_ids=kwargs.get('selected_tag_public_ids'),
        )
        kwargs.pop('selected_tag_public_ids', None)
        return BotConversaDispatchCreateForm(
            *args,
            flow_choices=self.build_flow_choices(),
            person_choices=person_choices,
            tag_choices=self.build_tag_choices(),
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
        has_loaded_people = False
        person_rows = []

        if self.request.GET.get('load') == '1' and list_form.is_valid():
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
                'create_form': kwargs.get('create_form') or PersonCreateForm(),
            }
        )
        return context


class BotConversaPersonCreateView(BotConversaOperatorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = PersonCreateForm(request.POST)
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
            BotConversaPeopleService.create_person(
                user=request.user,
                organization=self.active_organization,
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
                phone=form.cleaned_data['phone'],
                email=form.cleaned_data['email'],
            )
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect('bot_conversa:people')

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
        form = BotConversaBulkPersonSyncForm(request.POST, person_choices=self.build_person_choices())
        next_url = request.POST.get('next') or 'bot_conversa:people'

        if not form.is_valid():
            messages.error(request, form.errors.get('person_public_ids', ['Selecione pessoas válidas.'])[0])
            return redirect(next_url)

        persons = list(
            PersonRepository.list_for_organization_and_public_ids(
                self.active_organization,
                form.cleaned_data['person_public_ids'],
            )
        )
        try:
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
                'recent_dispatches': BotConversaFlowDispatchRepository.list_recent_for_organization(
                    self.active_organization,
                ),
                'initial_bot_conversa_audience_count': len(
                    self.build_person_choices(tag_public_ids=selected_tag_public_ids)
                ),
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
        form = self.build_dispatch_form(request.POST)
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
                    selected_tag_public_ids=request.POST.getlist('tag_public_ids'),
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

        try:
            dispatch = BotConversaDispatchService.create_dispatch(
                user=request.user,
                organization=self.active_organization,
                flow_cache=flow_cache,
                persons=persons,
                tags=tags,
                min_delay_seconds=form.cleaned_data['min_delay_seconds'],
                max_delay_seconds=form.cleaned_data['max_delay_seconds'],
            )
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect('bot_conversa:dispatches')

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
