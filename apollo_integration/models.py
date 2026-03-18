from django.conf import settings
from django.db import models
from common.models import PublicIdentifierMixin, TimeStampedModel
from companies.models import Company
from integrations.models import OrganizationAppInstallation
from organizations.models import Organization
from people.models import Person


class OrganizationScopedQuerySet(models.QuerySet):
    def for_organization(self, organization):
        return self.filter(organization=organization)


class ApolloCompanySyncLogQuerySet(OrganizationScopedQuerySet):
    def with_related_objects(self):
        return self.select_related('organization', 'installation', 'company', 'actor')


class ApolloCompanySyncLog(TimeStampedModel):
    class Action(models.TextChoices):
        IMPORT = 'import', 'Importacao'
        SYNC_TO_HUBSPOT = 'sync_to_hubspot', 'Sincronizacao HubSpot'

    class Outcome(models.TextChoices):
        SUCCESS = 'success', 'Sucesso'
        ERROR = 'error', 'Erro'

    organization = models.ForeignKey(
        Organization,
        related_name='apollo_company_sync_logs',
        on_delete=models.CASCADE,
    )
    installation = models.ForeignKey(
        OrganizationAppInstallation,
        related_name='apollo_company_sync_logs',
        on_delete=models.CASCADE,
    )
    company = models.ForeignKey(
        Company,
        related_name='apollo_sync_logs',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='apollo_company_sync_logs',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    message = models.CharField(max_length=255, blank=True)
    remote_payload = models.JSONField(default=dict, blank=True)

    objects = ApolloCompanySyncLogQuerySet.as_manager()

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.organization.name} - {self.action} - {self.outcome}'


class ApolloUsageSnapshotQuerySet(OrganizationScopedQuerySet):
    def with_related_objects(self):
        return self.select_related('organization', 'installation')


class ApolloUsageSnapshot(PublicIdentifierMixin, TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        related_name='apollo_usage_snapshots',
        on_delete=models.CASCADE,
    )
    installation = models.ForeignKey(
        OrganizationAppInstallation,
        related_name='apollo_usage_snapshots',
        on_delete=models.CASCADE,
    )
    fetched_at = models.DateTimeField()
    raw_payload = models.JSONField(default=dict, blank=True)
    credits_used = models.PositiveIntegerField(null=True, blank=True)
    credits_remaining = models.PositiveIntegerField(null=True, blank=True)
    rate_limit_per_minute = models.PositiveIntegerField(null=True, blank=True)
    rate_limit_per_hour = models.PositiveIntegerField(null=True, blank=True)
    rate_limit_per_day = models.PositiveIntegerField(null=True, blank=True)

    objects = ApolloUsageSnapshotQuerySet.as_manager()

    class Meta:
        ordering = ('-fetched_at', '-created_at')

    def __str__(self):
        return f'{self.organization.name} - Apollo usage'


class ApolloPeopleEnrichmentJobQuerySet(OrganizationScopedQuerySet):
    def with_related_objects(self):
        return self.select_related('organization', 'installation', 'actor')


class ApolloPeopleEnrichmentJob(PublicIdentifierMixin, TimeStampedModel):
    class Status(models.TextChoices):
        COMPLETED = 'completed', 'Concluido'
        WEBHOOK_PENDING = 'webhook_pending', 'Aguardando webhook'
        COMPLETED_WITH_ERRORS = 'completed_with_errors', 'Concluido com erros'

    organization = models.ForeignKey(
        Organization,
        related_name='apollo_people_enrichment_jobs',
        on_delete=models.CASCADE,
    )
    installation = models.ForeignKey(
        OrganizationAppInstallation,
        related_name='apollo_people_enrichment_jobs',
        on_delete=models.CASCADE,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='apollo_people_enrichment_jobs',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.COMPLETED)
    fetch_phone = models.BooleanField(default=False)
    webhook_token = models.CharField(max_length=128, blank=True, default='')
    total_people = models.PositiveIntegerField(default=0)
    processed_people = models.PositiveIntegerField(default=0)
    success_people = models.PositiveIntegerField(default=0)
    failed_people = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    request_payload = models.JSONField(default=dict, blank=True)
    last_webhook_payload = models.JSONField(default=dict, blank=True)

    objects = ApolloPeopleEnrichmentJobQuerySet.as_manager()

    class Meta:
        ordering = ('-started_at', '-created_at')

    def __str__(self):
        return f'{self.organization.name} - Apollo enrichment - {self.status}'


class ApolloPeopleEnrichmentItemQuerySet(models.QuerySet):
    def with_related_objects(self):
        return self.select_related('job', 'person', 'organization')


class ApolloPeopleEnrichmentItem(TimeStampedModel):
    class Status(models.TextChoices):
        COMPLETED = 'completed', 'Concluido'
        WAITING_WEBHOOK = 'waiting_webhook', 'Aguardando webhook'
        FAILED = 'failed', 'Falhou'

    organization = models.ForeignKey(
        Organization,
        related_name='apollo_people_enrichment_items',
        on_delete=models.CASCADE,
    )
    job = models.ForeignKey(
        ApolloPeopleEnrichmentJob,
        related_name='items',
        on_delete=models.CASCADE,
    )
    person = models.ForeignKey(
        Person,
        related_name='apollo_enrichment_items',
        on_delete=models.CASCADE,
    )
    apollo_person_id = models.CharField(max_length=128, db_index=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.COMPLETED)
    requested_phone = models.BooleanField(default=False)
    email_enriched = models.BooleanField(default=False)
    phone_enriched = models.BooleanField(default=False)
    error_message = models.CharField(max_length=255, blank=True, default='')
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    webhook_payload = models.JSONField(default=dict, blank=True)
    webhook_received_at = models.DateTimeField(null=True, blank=True)

    objects = ApolloPeopleEnrichmentItemQuerySet.as_manager()

    class Meta:
        ordering = ('created_at',)
        constraints = [
            models.UniqueConstraint(
                fields=('job', 'apollo_person_id'),
                name='unique_apollo_people_enrichment_item_per_job',
            ),
        ]

    def __str__(self):
        return f'{self.person.full_name} - {self.status}'
