from django.conf import settings
from django.db import models
from common.models import PublicIdentifierMixin, TimeStampedModel
from companies.models import Company
from integrations.models import OrganizationAppInstallation
from organizations.models import Organization


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
