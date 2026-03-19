from django.conf import settings
from django.db import models

from common.models import PublicIdentifierMixin, TimeStampedModel
from organizations.models import Organization


class ImportJobQuerySet(models.QuerySet):
    def for_organization(self, organization):
        return self.filter(organization=organization)

    def with_related_objects(self):
        return self.select_related('organization', 'created_by', 'updated_by')


class ImportJobItemQuerySet(models.QuerySet):
    def for_job(self, job):
        return self.filter(job=job, organization=job.organization)

    def with_related_objects(self):
        return self.select_related('job', 'organization')

    def pending(self):
        return self.filter(status=self.model.Status.PENDING)


class ImportJob(PublicIdentifierMixin, TimeStampedModel):
    class EntityType(models.TextChoices):
        PEOPLE = 'people', 'Pessoas'
        COMPANIES = 'companies', 'Empresas'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        RUNNING = 'running', 'Em andamento'
        COMPLETED = 'completed', 'Concluido'
        COMPLETED_WITH_ERRORS = 'completed_with_errors', 'Concluido com erros'
        FAILED = 'failed', 'Falhou'

    organization = models.ForeignKey(
        Organization,
        related_name='import_jobs',
        on_delete=models.CASCADE,
    )
    entity_type = models.CharField(max_length=24, choices=EntityType.choices)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    source_filename = models.CharField(max_length=255)
    stored_file_path = models.CharField(max_length=512, blank=True)
    total_rows = models.PositiveIntegerField(default=0)
    processed_rows = models.PositiveIntegerField(default=0)
    success_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_summary = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_import_jobs',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='updated_import_jobs',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    objects = ImportJobQuerySet.as_manager()

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=('organization', 'entity_type', 'status')),
        ]

    @property
    def progress_percent(self):
        if self.total_rows == 0:
            return 0
        return int((self.processed_rows / self.total_rows) * 100)


class ImportJobItem(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        SUCCESS = 'success', 'Sucesso'
        FAILED = 'failed', 'Falhou'

    organization = models.ForeignKey(
        Organization,
        related_name='import_job_items',
        on_delete=models.CASCADE,
    )
    job = models.ForeignKey(
        ImportJob,
        related_name='items',
        on_delete=models.CASCADE,
    )
    row_number = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    message = models.CharField(max_length=255, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    objects = ImportJobItemQuerySet.as_manager()

    class Meta:
        ordering = ('row_number',)
        constraints = [
            models.UniqueConstraint(
                fields=('job', 'row_number'),
                name='unique_import_job_row_number',
            ),
        ]
        indexes = [
            models.Index(fields=('organization', 'job', 'status')),
        ]
