from django.conf import settings
from django.db import models

from common.models import PublicIdentifierMixin, TimeStampedModel
from common.phone import format_phone_display, normalize_phone
from integrations.models import OrganizationAppInstallation
from organizations.models import Organization
from people.models import Person


class OrganizationScopedQuerySet(models.QuerySet):
    def for_organization(self, organization):
        return self.filter(organization=organization)


class BotConversaContactQuerySet(OrganizationScopedQuerySet):
    def active(self):
        return self.exclude(sync_status='archived')

    def with_related_objects(self):
        return self.select_related('organization', 'installation', 'person', 'created_by', 'updated_by')


class BotConversaFlowCacheQuerySet(OrganizationScopedQuerySet):
    def with_related_objects(self):
        return self.select_related('organization', 'installation')

    def selectable(self):
        return self.filter(
            status__in=[
                self.model.Status.ACTIVE,
                self.model.Status.UNKNOWN,
            ]
        )


class BotConversaTagQuerySet(OrganizationScopedQuerySet):
    def with_related_objects(self):
        return self.select_related('organization', 'installation')


class BotConversaPersonTagQuerySet(OrganizationScopedQuerySet):
    def with_related_objects(self):
        return self.select_related('organization', 'installation', 'person', 'tag', 'contact_link', 'created_by', 'updated_by')


class BotConversaFlowDispatchQuerySet(OrganizationScopedQuerySet):
    def with_related_objects(self):
        return self.select_related('organization', 'installation', 'flow', 'created_by', 'updated_by')


class BotConversaFlowDispatchItemQuerySet(OrganizationScopedQuerySet):
    def with_related_objects(self):
        return self.select_related('organization', 'dispatch', 'person', 'contact_link')

    def pending(self):
        return self.filter(status=self.model.Status.PENDING)


class BotConversaContact(PublicIdentifierMixin, TimeStampedModel):
    class SyncStatus(models.TextChoices):
        SYNCED = 'synced', 'Sincronizado'
        PENDING = 'pending', 'Pendente'
        STALE = 'stale', 'Desatualizado'
        ERROR = 'error', 'Erro'
        ARCHIVED = 'archived', 'Arquivado'

    organization = models.ForeignKey(
        Organization,
        related_name='bot_conversa_contacts',
        on_delete=models.CASCADE,
    )
    installation = models.ForeignKey(
        OrganizationAppInstallation,
        related_name='bot_conversa_contacts',
        on_delete=models.CASCADE,
    )
    person = models.ForeignKey(
        Person,
        related_name='bot_conversa_contacts',
        on_delete=models.CASCADE,
    )
    external_subscriber_id = models.CharField(max_length=128)
    external_name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=32)
    normalized_phone = models.CharField(max_length=16, db_index=True)
    sync_status = models.CharField(max_length=16, choices=SyncStatus.choices, default=SyncStatus.PENDING)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error_message = models.CharField(max_length=255, blank=True)
    remote_payload = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_bot_conversa_contacts',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='updated_bot_conversa_contacts',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    objects = BotConversaContactQuerySet.as_manager()

    class Meta:
        ordering = ('person__first_name', 'person__last_name', 'normalized_phone')
        constraints = [
            models.UniqueConstraint(
                fields=('organization', 'installation', 'person'),
                name='unique_bot_conversa_contact_per_person',
            ),
            models.UniqueConstraint(
                fields=('organization', 'external_subscriber_id'),
                name='unique_bot_conversa_subscriber_per_organization',
            ),
        ]

    def save(self, *args, **kwargs):
        self.normalized_phone = normalize_phone(self.phone)
        self.phone = format_phone_display(self.normalized_phone)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.person.full_name} - {self.external_subscriber_id}'


class BotConversaFlowCache(PublicIdentifierMixin, TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Ativo'
        DRAFT = 'draft', 'Rascunho'
        PAUSED = 'paused', 'Pausado'
        UNKNOWN = 'unknown', 'Desconhecido'

    organization = models.ForeignKey(
        Organization,
        related_name='bot_conversa_flows',
        on_delete=models.CASCADE,
    )
    installation = models.ForeignKey(
        OrganizationAppInstallation,
        related_name='bot_conversa_flows',
        on_delete=models.CASCADE,
    )
    external_flow_id = models.CharField(max_length=128)
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UNKNOWN)
    description = models.TextField(blank=True)
    last_synced_at = models.DateTimeField()
    raw_payload = models.JSONField(default=dict, blank=True)

    objects = BotConversaFlowCacheQuerySet.as_manager()

    class Meta:
        ordering = ('name',)
        constraints = [
            models.UniqueConstraint(
                fields=('organization', 'installation', 'external_flow_id'),
                name='unique_bot_conversa_flow_per_installation',
            ),
        ]

    def __str__(self):
        return self.name


class BotConversaTag(PublicIdentifierMixin, TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        related_name='bot_conversa_tags',
        on_delete=models.CASCADE,
    )
    installation = models.ForeignKey(
        OrganizationAppInstallation,
        related_name='bot_conversa_tags',
        on_delete=models.CASCADE,
    )
    external_tag_id = models.CharField(max_length=128)
    name = models.CharField(max_length=255)
    last_synced_at = models.DateTimeField()
    raw_payload = models.JSONField(default=dict, blank=True)

    objects = BotConversaTagQuerySet.as_manager()

    class Meta:
        ordering = ('name',)
        constraints = [
            models.UniqueConstraint(
                fields=('organization', 'installation', 'external_tag_id'),
                name='unique_bot_conversa_tag_per_installation',
            ),
        ]

    def __str__(self):
        return self.name


class BotConversaPersonTag(PublicIdentifierMixin, TimeStampedModel):
    class SyncStatus(models.TextChoices):
        SYNCED = 'synced', 'Sincronizado'
        ERROR = 'error', 'Erro'

    organization = models.ForeignKey(
        Organization,
        related_name='bot_conversa_person_tags',
        on_delete=models.CASCADE,
    )
    installation = models.ForeignKey(
        OrganizationAppInstallation,
        related_name='bot_conversa_person_tags',
        on_delete=models.CASCADE,
    )
    person = models.ForeignKey(
        Person,
        related_name='bot_conversa_person_tags',
        on_delete=models.CASCADE,
    )
    tag = models.ForeignKey(
        BotConversaTag,
        related_name='person_links',
        on_delete=models.CASCADE,
    )
    contact_link = models.ForeignKey(
        BotConversaContact,
        related_name='tag_links',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    external_subscriber_id = models.CharField(max_length=128, blank=True)
    sync_status = models.CharField(max_length=16, choices=SyncStatus.choices, default=SyncStatus.SYNCED)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error_message = models.CharField(max_length=255, blank=True)
    remote_payload = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_bot_conversa_person_tags',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='updated_bot_conversa_person_tags',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    objects = BotConversaPersonTagQuerySet.as_manager()

    class Meta:
        ordering = ('tag__name', 'person__first_name', 'person__last_name')
        constraints = [
            models.UniqueConstraint(
                fields=('organization', 'person', 'tag'),
                name='unique_bot_conversa_tag_per_person',
            ),
        ]
        indexes = [
            models.Index(fields=('organization', 'tag')),
            models.Index(fields=('organization', 'person')),
        ]

    def __str__(self):
        return f'{self.person.full_name} - {self.tag.name}'


class BotConversaSyncLog(TimeStampedModel):
    class Action(models.TextChoices):
        LOOKUP = 'lookup', 'Consulta'
        CREATE = 'create', 'Criacao'
        LINK = 'link', 'Vinculo'

    class Outcome(models.TextChoices):
        SUCCESS = 'success', 'Sucesso'
        NOT_FOUND = 'not_found', 'Não encontrado'
        ERROR = 'error', 'Erro'

    organization = models.ForeignKey(
        Organization,
        related_name='bot_conversa_sync_logs',
        on_delete=models.CASCADE,
    )
    installation = models.ForeignKey(
        OrganizationAppInstallation,
        related_name='bot_conversa_sync_logs',
        on_delete=models.CASCADE,
    )
    person = models.ForeignKey(
        Person,
        related_name='bot_conversa_sync_logs',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    contact_link = models.ForeignKey(
        BotConversaContact,
        related_name='sync_logs',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='bot_conversa_sync_logs',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=16, choices=Action.choices)
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    message = models.CharField(max_length=255, blank=True)
    remote_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=('organization', 'action', 'outcome')),
        ]

    def __str__(self):
        return f'{self.organization.name} - {self.action} - {self.outcome}'


class BotConversaFlowDispatch(PublicIdentifierMixin, TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        RUNNING = 'running', 'Em andamento'
        PAUSED = 'paused', 'Pausado'
        COMPLETED = 'completed', 'Concluido'
        COMPLETED_WITH_ERRORS = 'completed_with_errors', 'Concluido com erros'
        FAILED = 'failed', 'Falhou'

    organization = models.ForeignKey(
        Organization,
        related_name='bot_conversa_flow_dispatches',
        on_delete=models.CASCADE,
    )
    installation = models.ForeignKey(
        OrganizationAppInstallation,
        related_name='bot_conversa_flow_dispatches',
        on_delete=models.CASCADE,
    )
    flow = models.ForeignKey(
        BotConversaFlowCache,
        related_name='dispatches',
        on_delete=models.PROTECT,
    )
    external_flow_id = models.CharField(max_length=128)
    flow_name = models.CharField(max_length=255)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    total_items = models.PositiveIntegerField(default=0)
    processed_items = models.PositiveIntegerField(default=0)
    success_items = models.PositiveIntegerField(default=0)
    failed_items = models.PositiveIntegerField(default=0)
    min_delay_seconds = models.PositiveIntegerField(default=0)
    max_delay_seconds = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_summary = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_bot_conversa_dispatches',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='updated_bot_conversa_dispatches',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    objects = BotConversaFlowDispatchQuerySet.as_manager()

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=('organization', 'status')),
        ]

    def __str__(self):
        return f'{self.flow_name} - {self.organization.name}'

    @property
    def progress_percent(self):
        if self.total_items == 0:
            return 0
        return int((self.processed_items / self.total_items) * 100)


class BotConversaFlowDispatchItem(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        RUNNING = 'running', 'Em andamento'
        SUCCESS = 'success', 'Sucesso'
        FAILED = 'failed', 'Falhou'
        SKIPPED = 'skipped', 'Ignorado'

    organization = models.ForeignKey(
        Organization,
        related_name='bot_conversa_flow_dispatch_items',
        on_delete=models.CASCADE,
    )
    dispatch = models.ForeignKey(
        BotConversaFlowDispatch,
        related_name='items',
        on_delete=models.CASCADE,
    )
    person = models.ForeignKey(
        Person,
        related_name='bot_conversa_flow_dispatch_items',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    contact_link = models.ForeignKey(
        BotConversaContact,
        related_name='dispatch_items',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    target_name = models.CharField(max_length=255)
    target_phone = models.CharField(max_length=32)
    normalized_phone = models.CharField(max_length=16, db_index=True)
    external_subscriber_id = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.CharField(max_length=255, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)

    objects = BotConversaFlowDispatchItemQuerySet.as_manager()

    class Meta:
        ordering = ('created_at', 'target_name')
        constraints = [
            models.UniqueConstraint(
                fields=('dispatch', 'normalized_phone'),
                name='unique_bot_conversa_dispatch_phone',
            ),
        ]
        indexes = [
            models.Index(fields=('dispatch', 'status')),
            models.Index(fields=('organization', 'status')),
        ]

    def save(self, *args, **kwargs):
        self.normalized_phone = normalize_phone(self.target_phone)
        self.target_phone = format_phone_display(self.normalized_phone)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.dispatch.flow_name} - {self.target_name}'
