from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.generic import TemplateView

from gmail_integration.exceptions import GmailApiError, GmailConfigurationError
from gmail_integration.forms import GmailCredentialSaveForm, GmailDispatchCreateForm, GmailTemplateForm
from gmail_integration.repositories import (
    GmailCredentialRepository,
    GmailDispatchRepository,
    GmailDispatchRecipientRepository,
    GmailTemplateRepository,
)
from gmail_integration.services import (
    GmailAuthorizationService,
    GmailCredentialService,
    GmailDashboardService,
    GmailDispatchService,
    GmailInstallationService,
    GmailTemplateService,
)
from people.repositories import PersonRepository


class GmailAccessMixin(LoginRequiredMixin):
    missing_organization_message = 'Escolha ou crie uma organizacao antes de acessar o Gmail.'
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
            self.installation = GmailInstallationService.get_installation(
                organization=active_organization,
            )
        except (GmailConfigurationError, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect(self.missing_installation_redirect_url)

        request.gmail_installation = self.installation
        self.active_organization = active_organization
        self.active_membership = active_membership
        return None

    def dispatch(self, request, *args, **kwargs):
        redirect_response = self.prepare_request_context(request)
        if redirect_response is not None:
            return redirect_response
        return super().dispatch(request, *args, **kwargs)

    def build_person_choices(self, *, only_unsent=False):
        persons = [
            person
            for person in PersonRepository.list_for_organization(self.active_organization)
            if person.email
        ]

        if only_unsent:
            sent_person_ids = set(
                GmailDispatchRecipientRepository.list_sent_person_ids_for_organization(
                    self.active_organization,
                )
            )
            persons = [person for person in persons if person.id not in sent_person_ids]

        return [
            (str(person.public_id), f'{person.full_name} - {person.email}')
            for person in persons
        ]

    def build_template_choices(self):
        return [
            (str(template.public_id), template.name)
            for template in GmailTemplateRepository.list_active_for_organization(self.active_organization)
        ]

    @staticmethod
    def build_template_variables():
        return [
            {
                'token': '${nome}',
                'label': 'Nome',
                'description': 'Primeiro nome da pessoa.',
                'example': 'Ola ${nome}, tudo bem?',
            },
            {
                'token': '${sobrenome}',
                'label': 'Sobrenome',
                'description': 'Sobrenome da pessoa.',
                'example': 'Equipe ${sobrenome}',
            },
            {
                'token': '${email}',
                'label': 'E-mail',
                'description': 'E-mail cadastrado no CRM.',
                'example': 'Estamos escrevendo para ${email}.',
            },
        ]

    def build_dispatch_form(self, *args, **kwargs):
        return GmailDispatchCreateForm(
            *args,
            template_choices=self.build_template_choices(),
            person_choices=self.build_person_choices(),
            **kwargs,
        )

    def get_module_tabs(self):
        return [
            {'label': 'Visao geral', 'url': 'gmail_integration:dashboard', 'key': 'dashboard'},
            {'label': 'Configuracao', 'url': 'gmail_integration:settings', 'key': 'settings'},
            {'label': 'Templates', 'url': 'gmail_integration:templates', 'key': 'templates'},
            {'label': 'Disparos', 'url': 'gmail_integration:dispatches', 'key': 'dispatches'},
        ]

    def build_base_context(self, *, active_tab):
        return {
            'gmail_installation': self.installation,
            'gmail_tabs': self.get_module_tabs(),
            'gmail_active_tab': active_tab,
            'can_manage_gmail': self.active_membership.can_manage_integrations,
            'gmail_template_variables': self.build_template_variables(),
        }


class GmailOperatorRequiredMixin(GmailAccessMixin):
    def dispatch(self, request, *args, **kwargs):
        redirect_response = self.prepare_request_context(request)
        if redirect_response is not None:
            return redirect_response

        if not self.active_membership.can_manage_integrations:
            messages.error(request, 'Somente proprietarios e administradores podem operar acoes do Gmail.')
            return redirect('gmail_integration:dashboard')

        return super(GmailAccessMixin, self).dispatch(request, *args, **kwargs)


class GmailDashboardView(GmailAccessMixin, TemplateView):
    template_name = 'gmail_integration/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.build_base_context(active_tab='dashboard'))
        try:
            summary = GmailDashboardService.build_summary(organization=self.active_organization)
        except GmailConfigurationError:
            summary = {
                'installation': self.installation,
                'credential': GmailCredentialRepository.get_for_organization(self.active_organization),
                'template_count': GmailTemplateRepository.list_for_organization(self.active_organization).count(),
                'dispatch_count': GmailDispatchRepository.list_for_organization(self.active_organization).count(),
                'recent_dispatches': GmailDispatchRepository.list_recent_for_organization(self.active_organization, limit=5),
            }
        context['summary'] = summary
        return context


class GmailSettingsView(GmailAccessMixin, TemplateView):
    template_name = 'gmail_integration/settings.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current_credential = GmailCredentialRepository.get_for_organization(self.active_organization)

        context.update(self.build_base_context(active_tab='settings'))
        context.update(
            {
                'credential': current_credential,
                'credential_form': kwargs.get('credential_form') or GmailCredentialSaveForm(),
            }
        )
        return context


class GmailCredentialSaveView(GmailOperatorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = GmailCredentialSaveForm(request.POST, request.FILES)
        if not form.is_valid():
            view = GmailSettingsView()
            view.request = request
            view.args = args
            view.kwargs = kwargs
            view.installation = self.installation
            view.active_organization = self.active_organization
            view.active_membership = self.active_membership
            return view.render_to_response(view.get_context_data(credential_form=form))

        try:
            GmailCredentialService.save_configuration(
                user=request.user,
                organization=self.active_organization,
                credentials_file=form.cleaned_data['credentials_file'],
                token_file=form.cleaned_data['token_file'],
            )
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, exc.messages[0] if hasattr(exc, 'messages') and exc.messages else str(exc))
            return redirect('gmail_integration:settings')

        messages.success(request, 'Configuracao do Gmail salva com sucesso.')
        return redirect('gmail_integration:settings')


class GmailTemplatesView(GmailAccessMixin, TemplateView):
    template_name = 'gmail_integration/templates.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.build_base_context(active_tab='templates'))
        context.update(
            {
                'templates_list': GmailTemplateRepository.list_for_organization(self.active_organization),
                'template_form': kwargs.get('template_form') or GmailTemplateForm(),
            }
        )
        return context


class GmailTemplateCreateView(GmailOperatorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = GmailTemplateForm(request.POST)
        if not form.is_valid():
            view = GmailTemplatesView()
            view.request = request
            view.args = args
            view.kwargs = kwargs
            view.installation = self.installation
            view.active_organization = self.active_organization
            view.active_membership = self.active_membership
            return view.render_to_response(view.get_context_data(template_form=form))

        try:
            GmailTemplateService.create_template(
                user=request.user,
                organization=self.active_organization,
                name=form.cleaned_data['name'],
                subject=form.cleaned_data['subject'],
                body=form.cleaned_data['body'],
                is_active=form.cleaned_data['is_active'],
            )
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, exc.messages[0] if hasattr(exc, 'messages') and exc.messages else str(exc))
            return redirect('gmail_integration:templates')

        messages.success(request, 'Template salvo com sucesso.')
        return redirect('gmail_integration:templates')


class GmailTemplateUpdateView(GmailOperatorRequiredMixin, TemplateView):
    template_name = 'gmail_integration/template_edit.html'

    def get_template_object(self):
        return GmailTemplateRepository.get_for_organization_and_public_id(
            self.active_organization,
            self.kwargs['template_public_id'],
        )

    def dispatch(self, request, *args, **kwargs):
        redirect_response = self.prepare_request_context(request)
        if redirect_response is not None:
            return redirect_response

        self.template_object = self.get_template_object()
        if self.template_object is None:
            messages.error(request, 'O template selecionado nao foi encontrado.')
            return redirect('gmail_integration:templates')

        if not self.active_membership.can_manage_integrations:
            messages.error(request, 'Somente proprietarios e administradores podem editar templates do Gmail.')
            return redirect('gmail_integration:dashboard')

        return super(GmailAccessMixin, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = kwargs.get('template_form') or GmailTemplateForm(
            initial={
                'name': self.template_object.name,
                'subject': self.template_object.subject,
                'body': self.template_object.body,
                'is_active': self.template_object.is_active,
            }
        )
        context.update(self.build_base_context(active_tab='templates'))
        context.update(
            {
                'template_object': self.template_object,
                'template_form': form,
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        form = GmailTemplateForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(template_form=form))

        try:
            GmailTemplateService.update_template(
                user=request.user,
                organization=self.active_organization,
                template=self.template_object,
                name=form.cleaned_data['name'],
                subject=form.cleaned_data['subject'],
                body=form.cleaned_data['body'],
                is_active=form.cleaned_data['is_active'],
            )
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, exc.messages[0] if hasattr(exc, 'messages') and exc.messages else str(exc))
            return self.render_to_response(self.get_context_data(template_form=form))

        messages.success(request, 'Template atualizado com sucesso.')
        return redirect('gmail_integration:templates')


class GmailDispatchesView(GmailAccessMixin, TemplateView):
    template_name = 'gmail_integration/dispatches.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.build_base_context(active_tab='dispatches'))
        context.update(
            {
                'dispatches': GmailDispatchRepository.list_for_organization(self.active_organization),
                'dispatch_form': kwargs.get('dispatch_form') or self.build_dispatch_form(),
                'available_variables': [variable['token'] for variable in self.build_template_variables()],
                'initial_gmail_audience_count': len(self.build_person_choices()),
            }
        )
        return context


class GmailDispatchCreateView(GmailOperatorRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = self.build_dispatch_form(request.POST)
        if not form.is_valid():
            view = GmailDispatchesView()
            view.request = request
            view.args = args
            view.kwargs = kwargs
            view.installation = self.installation
            view.active_organization = self.active_organization
            view.active_membership = self.active_membership
            return view.render_to_response(view.get_context_data(dispatch_form=form))

        template = None
        if form.cleaned_data['template_public_id']:
            template = GmailTemplateRepository.get_for_organization_and_public_id(
                self.active_organization,
                form.cleaned_data['template_public_id'],
            )
            if template is None:
                messages.error(request, 'O template selecionado nao foi encontrado.')
                return redirect('gmail_integration:dispatches')

        to_people = list(
            PersonRepository.list_for_organization_and_public_ids(
                self.active_organization,
                form.cleaned_data['person_public_ids'],
            )
        )
        try:
            dispatch = GmailDispatchService.create_dispatch(
                user=request.user,
                organization=self.active_organization,
                template=template,
                to_people=to_people,
                cc_emails=form.cleaned_data['cc_emails'],
                min_delay_seconds=form.cleaned_data['min_delay_seconds'],
                max_delay_seconds=form.cleaned_data['max_delay_seconds'],
            )
        except (GmailApiError, GmailConfigurationError, PermissionDenied, ValidationError) as exc:
            messages.error(request, exc.messages[0] if hasattr(exc, 'messages') and exc.messages else str(exc))
            return redirect('gmail_integration:dispatches')

        messages.success(request, 'Disparo do Gmail criado. O processamento continuara na tela de status.')
        return redirect('gmail_integration:dispatch_detail', dispatch_public_id=dispatch.public_id)


class GmailDispatchDetailView(GmailAccessMixin, TemplateView):
    template_name = 'gmail_integration/dispatch_detail.html'

    def dispatch(self, request, *args, **kwargs):
        redirect_response = self.prepare_request_context(request)
        if redirect_response is not None:
            return redirect_response

        self.dispatch_object = GmailDispatchRepository.get_for_organization_and_public_id(
            self.active_organization,
            kwargs['dispatch_public_id'],
        )
        if self.dispatch_object is None:
            messages.error(request, 'O disparo selecionado nao foi encontrado.')
            return redirect('gmail_integration:dispatches')

        return super(GmailAccessMixin, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.build_base_context(active_tab='dispatches'))
        context.update(GmailDispatchService.build_dispatch_payload(dispatch=self.dispatch_object))
        return context


@method_decorator(never_cache, name='dispatch')
class GmailDispatchAudienceView(GmailAccessMixin, View):
    http_method_names = ['get']

    def get(self, request, *args, **kwargs):
        only_unsent = request.GET.get('only_unsent') == '1'
        person_choices = self.build_person_choices(only_unsent=only_unsent)
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
                    'Nenhuma pessoa sem envio anterior no Gmail esta disponivel para este disparo.'
                    if only_unsent
                    else 'Nenhuma pessoa com e-mail cadastrado esta disponivel para este disparo.'
                ),
            }
        )
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response


@method_decorator(never_cache, name='dispatch')
class GmailDispatchProcessView(LoginRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        active_organization = getattr(request, 'active_organization', None)
        if active_organization is None:
            return self.build_json_response({'detail': 'Nenhuma organizacao ativa foi encontrada.'}, status=400)

        try:
            GmailAuthorizationService.ensure_operator_access(
                user=request.user,
                organization=active_organization,
            )
            GmailInstallationService.get_installation(organization=active_organization)
        except PermissionDenied as exc:
            return self.build_json_response({'detail': str(exc)}, status=403)
        except (GmailConfigurationError, ValidationError) as exc:
            return self.build_json_response({'detail': str(exc)}, status=400)

        dispatch = GmailDispatchRepository.get_for_organization_and_public_id(
            active_organization,
            kwargs['dispatch_public_id'],
        )
        if dispatch is None:
            raise Http404('Disparo nao encontrado.')

        try:
            dispatch = GmailDispatchService.process_dispatch(
                organization=active_organization,
                dispatch=dispatch,
            )
        except (GmailApiError, GmailConfigurationError, PermissionDenied, ValidationError) as exc:
            return self.build_json_response({'detail': str(exc)}, status=400)

        return self.build_json_response(
            GmailDispatchService.build_dispatch_payload(dispatch=dispatch)['status_payload'],
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
