from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.generic import TemplateView

from common.mixins import ActiveOrganizationRequiredMixin, OrganizationManagerRequiredMixin
from integrations.forms import ApiKeyRevealForm, ApiKeySaveForm, AppInstallForm
from integrations.repositories import AppCatalogRepository, AppInstallationRepository
from integrations.services import AppCredentialService, AppInstallationService, IntegrationCatalogService


class AppsCatalogView(ActiveOrganizationRequiredMixin, TemplateView):
    template_name = 'integrations/apps.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_membership = getattr(self.request, 'active_membership', None)
        context.update(
            {
                'app_cards': IntegrationCatalogService.build_catalog_state(
                    organization=self.request.active_organization,
                ),
                'install_form': AppInstallForm(),
                'can_manage_integrations': active_membership.can_manage_integrations if active_membership else False,
            }
        )
        return context


@method_decorator(never_cache, name='dispatch')
class ApiKeyManagementView(OrganizationManagerRequiredMixin, TemplateView):
    template_name = 'integrations/api_keys.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                'app_cards': IntegrationCatalogService.build_api_key_state(
                    organization=self.request.active_organization,
                ),
                'api_key_form': ApiKeySaveForm(),
                'reveal_form': ApiKeyRevealForm(),
            }
        )
        return context


class InstallAppView(OrganizationManagerRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = AppInstallForm(request.POST)
        next_url = request.POST.get('next') or 'integrations:apps'

        if not form.is_valid():
            messages.error(request, 'Escolha um aplicativo valido para instalar.')
            return redirect(next_url)

        app = AppCatalogRepository.get_active_by_public_id(form.cleaned_data['app_public_id'])
        if app is None:
            messages.error(request, 'O aplicativo selecionado nao foi encontrado.')
            return redirect(next_url)

        installation, was_created = AppInstallationService.install_app(
            user=request.user,
            organization=request.active_organization,
            app=app,
        )

        if was_created:
            messages.success(request, f'{installation.app.name} foi instalado na organizacao ativa.')
        else:
            messages.info(request, f'{installation.app.name} ja esta instalado.')

        return redirect(next_url)


class SaveApiKeyView(OrganizationManagerRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = ApiKeySaveForm(request.POST)
        next_url = request.POST.get('next') or 'integrations:api_keys'

        if not form.is_valid():
            for field_errors in form.errors.values():
                for error in field_errors:
                    messages.error(request, error)
            return redirect(next_url)

        installation = AppInstallationRepository.get_for_organization_and_public_id(
            request.active_organization,
            form.cleaned_data['installation_public_id'],
        )
        if installation is None:
            messages.error(request, 'A instalacao selecionada nao foi encontrada.')
            return redirect(next_url)

        try:
            credential, was_created = AppCredentialService.save_api_key(
                user=request.user,
                organization=request.active_organization,
                installation=installation,
                api_key=form.cleaned_data['api_key'],
            )
        except (PermissionDenied, ValidationError) as exc:
            message = exc.messages[0] if hasattr(exc, 'messages') and exc.messages else str(exc)
            messages.error(request, message)
            return redirect(next_url)

        action_label = 'salva' if was_created else 'mantida sem alteracoes'
        messages.success(
            request,
            f'Chave de API de {credential.app.name} {action_label} com sucesso.',
        )
        return redirect(next_url)


@method_decorator(never_cache, name='dispatch')
class RevealApiKeyView(LoginRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        active_organization = getattr(request, 'active_organization', None)
        active_membership = getattr(request, 'active_membership', None)

        if active_organization is None:
            return self.build_json_response({'detail': 'Nenhuma organizacao ativa foi encontrada.'}, status=400)

        if not active_membership or not active_membership.can_manage_integrations:
            return self.build_json_response({'detail': 'Voce nao tem permissao para visualizar chaves de API.'}, status=403)

        form = ApiKeyRevealForm(request.POST)
        if not form.is_valid():
            return self.build_json_response({'detail': 'Digite a palavra de confirmacao exatamente como solicitado.'}, status=400)

        installation = AppInstallationRepository.get_for_organization_and_public_id(
            active_organization,
            kwargs['installation_public_id'],
        )
        if installation is None:
            raise Http404('Credencial nao encontrada.')

        try:
            credential = AppCredentialService.reveal_api_key(
                user=request.user,
                organization=active_organization,
                installation=installation,
                confirmation_word=form.cleaned_data['confirmation_word'],
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )
        except PermissionDenied as exc:
            message = exc.messages[0] if hasattr(exc, 'messages') and exc.messages else str(exc)
            return self.build_json_response({'detail': message}, status=403)
        except ValidationError as exc:
            message = exc.messages[0] if hasattr(exc, 'messages') and exc.messages else str(exc)
            return self.build_json_response({'detail': message}, status=400)

        return self.build_json_response(
            {
                'api_key': credential.secret_value,
                'masked_value': credential.masked_value,
                'app_name': credential.app.name,
            },
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

    @staticmethod
    def get_client_ip(request):
        forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')
