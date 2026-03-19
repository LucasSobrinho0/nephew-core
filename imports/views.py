from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from common.mixins import ActiveOrganizationRequiredMixin
from imports.forms import ImportUploadForm
from imports.models import ImportJob
from imports.repositories import ImportJobRepository
from imports.services import ImportJobPresentationService, ImportJobService, ImportTemplateService


class ImportAccessMixin(LoginRequiredMixin, ActiveOrganizationRequiredMixin):
    def ensure_manage_access(self, request):
        membership = getattr(request, 'active_membership', None)
        if membership is None or not membership.can_manage_integrations:
            raise PermissionDenied('Somente proprietarios e administradores podem importar planilhas.')
        return membership


class ImportTemplateDownloadView(ImportAccessMixin, View):
    def get(self, request, *args, **kwargs):
        self.ensure_manage_access(request)
        entity_type = kwargs['entity_type']
        return ImportTemplateService.build_download_response(entity_type)


class ImportJobCreateView(ImportAccessMixin, View):
    entity_type = ''
    redirect_url_name = ''

    def post(self, request, *args, **kwargs):
        self.ensure_manage_access(request)
        form = ImportUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, form.errors.get('file', ['Envie uma planilha XLSX valida.'])[0])
            return redirect(self.redirect_url_name)

        try:
            job = ImportJobService.create_job(
                user=request.user,
                organization=request.active_organization,
                entity_type=self.entity_type,
                uploaded_file=form.cleaned_data['file'],
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if exc.messages else str(exc))
            return redirect(self.redirect_url_name)

        messages.success(request, 'Importacao iniciada com sucesso.')
        return redirect('imports:job_detail', job_public_id=job.public_id)


class PersonImportJobCreateView(ImportJobCreateView):
    entity_type = ImportJob.EntityType.PEOPLE
    redirect_url_name = 'people:index'


class CompanyImportJobCreateView(ImportJobCreateView):
    entity_type = ImportJob.EntityType.COMPANIES
    redirect_url_name = 'companies:index'


class ImportJobDetailView(ImportAccessMixin, TemplateView):
    template_name = 'imports/job_detail.html'

    def get_job(self):
        return ImportJobRepository.get_for_organization_and_public_id(
            self.request.active_organization,
            self.kwargs['job_public_id'],
        )

    def dispatch(self, request, *args, **kwargs):
        self.ensure_manage_access(request)
        self.job = self.get_job()
        if self.job is None:
            messages.error(request, 'O job de importacao selecionado nao foi encontrado.')
            return redirect('dashboard:home')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['job'] = self.job
        context['status_payload'] = ImportJobPresentationService.build_payload(self.job)
        return context


class ImportJobProgressView(ImportAccessMixin, View):
    def post(self, request, *args, **kwargs):
        self.ensure_manage_access(request)
        job = ImportJobRepository.get_for_organization_and_public_id(
            request.active_organization,
            kwargs['job_public_id'],
        )
        if job is None:
            return JsonResponse({'detail': 'Job de importacao nao encontrado.'}, status=404)
        return JsonResponse(ImportJobPresentationService.build_payload(job))
