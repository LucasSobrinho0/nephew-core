from django.conf import settings
from django.db import models

from common.encryption import APP_CREDENTIAL_ENCRYPTION_PURPOSE, DEFAULT_ENCRYPTION_PURPOSE
from common.fields import EncryptedTextField
from common.models import PublicIdentifierMixin, TimeStampedModel
from integrations.models import OrganizationAppInstallation
from organizations.models import Organization
from people.models import Person


class OrganizationScopedQuerySet(models.QuerySet):
    def for_organization(self, organization):
        return self.filter(organization=organization)


class GmailCredentialQuerySet(OrganizationScopedQuerySet):
    def with_related_objects(self):
        return self.select_related('organization', 'installation', 'created_by', 'updated_by')


class GmailTemplateQuerySet(OrganizationScopedQuerySet):
    def active(self):
        return self.filter(is_active=True)

    def with_related_objects(self):
        return self.select_related('organization', 'created_by', 'updated_by')


class GmailDispatchQuerySet(OrganizationScopedQuerySet):
    def with_related_objects(self):
        return self.select_related('organization', 'installation', 'template', 'created_by', 'updated_by')


class GmailDispatchRecipientQuerySet(OrganizationScopedQuerySet):
    def with_related_objects(self):
        return self.select_related('organization', 'dispatch', 'person')


class GmailCredential(PublicIdentifierMixin, TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        related_name='gmail_credentials',
        on_delete=models.CASCADE,
    )
    installation = models.OneToOneField(
        OrganizationAppInstallation,
        related_name='gmail_credential',
        on_delete=models.CASCADE,
    )
    sender_email = models.EmailField(max_length=254, blank=True, default='')
    credentials_json = EncryptedTextField(
        purpose=APP_CREDENTIAL_ENCRYPTION_PURPOSE,
        fallback_purposes=(DEFAULT_ENCRYPTION_PURPOSE,),
    )
    token_json = EncryptedTextField(
        purpose=APP_CREDENTIAL_ENCRYPTION_PURPOSE,
        fallback_purposes=(DEFAULT_ENCRYPTION_PURPOSE,),
    )
    scopes = models.JSONField(default=list, blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_gmail_credentials',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='updated_gmail_credentials',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    objects = GmailCredentialQuerySet.as_manager()

    class Meta:
        ordering = ('sender_email',)

    def __str__(self):
        return self.sender_email


class GmailTemplate(PublicIdentifierMixin, TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        related_name='gmail_templates',
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=120)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_gmail_templates',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='updated_gmail_templates',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    objects = GmailTemplateQuerySet.as_manager()

    class Meta:
        ordering = ('name',)
        constraints = [
            models.UniqueConstraint(
                fields=('organization', 'name'),
                name='unique_gmail_template_name_per_organization',
            ),
        ]

    def __str__(self):
        return self.name


class GmailDispatch(PublicIdentifierMixin, TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        RUNNING = 'running', 'Em andamento'
        COMPLETED = 'completed', 'Concluido'
        COMPLETED_WITH_ERRORS = 'completed_with_errors', 'Concluido com erros'
        FAILED = 'failed', 'Falhou'

    organization = models.ForeignKey(
        Organization,
        related_name='gmail_dispatches',
        on_delete=models.CASCADE,
    )
    installation = models.ForeignKey(
        OrganizationAppInstallation,
        related_name='gmail_dispatches',
        on_delete=models.CASCADE,
    )
    template = models.ForeignKey(
        GmailTemplate,
        related_name='dispatches',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    subject_snapshot = models.CharField(max_length=255)
    body_snapshot = models.TextField()
    cc_recipients_snapshot = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    total_recipients = models.PositiveIntegerField(default=0)
    processed_recipients = models.PositiveIntegerField(default=0)
    success_recipients = models.PositiveIntegerField(default=0)
    failed_recipients = models.PositiveIntegerField(default=0)
    min_delay_seconds = models.PositiveSmallIntegerField(default=0)
    max_delay_seconds = models.PositiveSmallIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_summary = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_gmail_dispatches',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='updated_gmail_dispatches',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    objects = GmailDispatchQuerySet.as_manager()

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return self.subject_snapshot


class GmailDispatchRecipient(PublicIdentifierMixin, TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        RUNNING = 'running', 'Em andamento'
        SENT = 'sent', 'Enviado'
        FAILED = 'failed', 'Falhou'

    organization = models.ForeignKey(
        Organization,
        related_name='gmail_dispatch_recipients',
        on_delete=models.CASCADE,
    )
    dispatch = models.ForeignKey(
        GmailDispatch,
        related_name='recipients',
        on_delete=models.CASCADE,
    )
    person = models.ForeignKey(
        Person,
        related_name='gmail_dispatch_recipients',
        on_delete=models.PROTECT,
    )
    email_snapshot = models.EmailField(max_length=254)
    first_name_snapshot = models.CharField(max_length=120)
    last_name_snapshot = models.CharField(max_length=120)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    gmail_message_id = models.CharField(max_length=255, blank=True)
    gmail_thread_id = models.CharField(max_length=255, blank=True)
    error_message = models.CharField(max_length=255, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    objects = GmailDispatchRecipientQuerySet.as_manager()

    class Meta:
        ordering = ('first_name_snapshot', 'last_name_snapshot', 'email_snapshot')
        constraints = [
            models.UniqueConstraint(
                fields=('dispatch', 'person'),
                name='unique_gmail_dispatch_recipient_per_person',
            ),
        ]

    def __str__(self):
        return self.email_snapshot
