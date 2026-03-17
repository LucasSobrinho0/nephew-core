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


class HubSpotPipelineCacheQuerySet(OrganizationScopedQuerySet):
    def with_related_objects(self):
        return self.select_related('organization', 'installation')


class HubSpotDealQuerySet(OrganizationScopedQuerySet):
    def with_related_objects(self):
        return self.select_related('organization', 'installation', 'company', 'pipeline', 'created_by', 'updated_by')


class HubSpotSyncLogQuerySet(OrganizationScopedQuerySet):
    def with_related_objects(self):
        return self.select_related('organization', 'installation', 'company', 'person', 'deal', 'actor')


class HubSpotPipelineCache(PublicIdentifierMixin, TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        related_name='hubspot_pipelines',
        on_delete=models.CASCADE,
    )
    installation = models.ForeignKey(
        OrganizationAppInstallation,
        related_name='hubspot_pipelines',
        on_delete=models.CASCADE,
    )
    hubspot_pipeline_id = models.CharField(max_length=128)
    name = models.CharField(max_length=255)
    object_type = models.CharField(max_length=64, default='deals')
    raw_payload = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField()

    objects = HubSpotPipelineCacheQuerySet.as_manager()

    class Meta:
        ordering = ('name',)
        constraints = [
            models.UniqueConstraint(
                fields=('organization', 'installation', 'hubspot_pipeline_id'),
                name='unique_hubspot_pipeline_per_installation',
            ),
        ]

    def __str__(self):
        return self.name


class HubSpotDeal(PublicIdentifierMixin, TimeStampedModel):
    class SyncStatus(models.TextChoices):
        SYNCED = 'synced', 'Sincronizado'
        ERROR = 'error', 'Erro'

    organization = models.ForeignKey(
        Organization,
        related_name='hubspot_deals',
        on_delete=models.CASCADE,
    )
    installation = models.ForeignKey(
        OrganizationAppInstallation,
        related_name='hubspot_deals',
        on_delete=models.CASCADE,
    )
    company = models.ForeignKey(
        Company,
        related_name='hubspot_deals',
        on_delete=models.PROTECT,
    )
    pipeline = models.ForeignKey(
        HubSpotPipelineCache,
        related_name='hubspot_deals',
        on_delete=models.PROTECT,
    )
    hubspot_deal_id = models.CharField(max_length=128, blank=True, default='', db_index=True)
    name = models.CharField(max_length=255)
    amount = models.CharField(max_length=64, blank=True)
    stage_id = models.CharField(max_length=128, blank=True)
    sync_status = models.CharField(max_length=16, choices=SyncStatus.choices, default=SyncStatus.SYNCED)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_hubspot_deals',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='updated_hubspot_deals',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    objects = HubSpotDealQuerySet.as_manager()

    class Meta:
        ordering = ('-created_at',)
        constraints = [
            models.UniqueConstraint(
                fields=('organization', 'hubspot_deal_id'),
                condition=~models.Q(hubspot_deal_id=''),
                name='unique_hubspot_deal_id_per_organization',
            ),
        ]

    def __str__(self):
        return self.name


class HubSpotSyncLog(TimeStampedModel):
    class EntityType(models.TextChoices):
        COMPANY = 'company', 'Empresa'
        PERSON = 'person', 'Pessoa'
        PIPELINE = 'pipeline', 'Pipeline'
        DEAL = 'deal', 'Deal'

    class Outcome(models.TextChoices):
        SUCCESS = 'success', 'Sucesso'
        ERROR = 'error', 'Erro'

    organization = models.ForeignKey(
        Organization,
        related_name='hubspot_sync_logs',
        on_delete=models.CASCADE,
    )
    installation = models.ForeignKey(
        OrganizationAppInstallation,
        related_name='hubspot_sync_logs',
        on_delete=models.CASCADE,
    )
    company = models.ForeignKey(
        Company,
        related_name='hubspot_sync_logs',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    person = models.ForeignKey(
        Person,
        related_name='hubspot_sync_logs',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    deal = models.ForeignKey(
        HubSpotDeal,
        related_name='hubspot_sync_logs',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='hubspot_sync_logs',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    entity_type = models.CharField(max_length=16, choices=EntityType.choices)
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    message = models.CharField(max_length=255, blank=True)
    remote_payload = models.JSONField(default=dict, blank=True)

    objects = HubSpotSyncLogQuerySet.as_manager()

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.entity_type} - {self.outcome}'
