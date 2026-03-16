from django.conf import settings
from django.db import models
from django.db.models import Q

from common.fields import EncryptedTextField
from common.encryption import APP_CREDENTIAL_ENCRYPTION_PURPOSE, DEFAULT_ENCRYPTION_PURPOSE
from common.models import PublicIdentifierMixin, TimeStampedModel
from integrations.constants import API_KEY_CREDENTIAL_TYPE
from organizations.models import Organization


class AppCatalogQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def ordered(self):
        return self.order_by('sort_order', 'name')


class OrganizationAppInstallationQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status='active')

    def for_organization(self, organization):
        return self.filter(organization=organization)

    def with_related_objects(self):
        return self.select_related('organization', 'app', 'created_by', 'updated_by')


class OrganizationAppCredentialQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status='active')

    def current(self):
        return self.active().order_by('-version', '-created_at')

    def for_installation(self, installation):
        return self.filter(installation=installation)


class AppCatalog(PublicIdentifierMixin, TimeStampedModel):
    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    icon_class = models.CharField(max_length=64, default='bi bi-grid-fill')
    supports_api_key = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=100)

    objects = AppCatalogQuerySet.as_manager()

    class Meta:
        ordering = ('sort_order', 'name')

    def __str__(self):
        return self.name


class OrganizationAppInstallation(PublicIdentifierMixin, TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Ativo'
        INACTIVE = 'inactive', 'Inativo'

    organization = models.ForeignKey(
        Organization,
        related_name='app_installations',
        on_delete=models.CASCADE,
    )
    app = models.ForeignKey(
        AppCatalog,
        related_name='installations',
        on_delete=models.CASCADE,
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_app_installations',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='updated_app_installations',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    objects = OrganizationAppInstallationQuerySet.as_manager()

    class Meta:
        ordering = ('app__sort_order', 'app__name')
        constraints = [
            models.UniqueConstraint(
                fields=('organization', 'app'),
                name='unique_organization_app_installation',
            ),
        ]

    def __str__(self):
        return f'{self.organization.name} - {self.app.name}'

    @property
    def is_installed(self):
        return self.status == self.Status.ACTIVE


class OrganizationAppCredential(PublicIdentifierMixin, TimeStampedModel):
    class CredentialType(models.TextChoices):
        API_KEY = API_KEY_CREDENTIAL_TYPE, 'Chave de API'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Ativo'
        INACTIVE = 'inactive', 'Inativo'
        REVOKED = 'revoked', 'Revogado'

    installation = models.ForeignKey(
        OrganizationAppInstallation,
        related_name='credentials',
        on_delete=models.CASCADE,
    )
    credential_type = models.CharField(max_length=32, choices=CredentialType.choices, default=CredentialType.API_KEY)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    secret_value = EncryptedTextField(
        purpose=APP_CREDENTIAL_ENCRYPTION_PURPOSE,
        fallback_purposes=(DEFAULT_ENCRYPTION_PURPOSE,),
    )
    masked_value = models.CharField(max_length=255)
    last_four = models.CharField(max_length=4, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_app_credentials',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='updated_app_credentials',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='revoked_app_credentials',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = OrganizationAppCredentialQuerySet.as_manager()

    class Meta:
        ordering = ('installation__app__sort_order', '-version', '-created_at')
        constraints = [
            models.UniqueConstraint(
                fields=('installation', 'credential_type', 'version'),
                name='unique_installation_credential_version',
            ),
            models.UniqueConstraint(
                fields=('installation', 'credential_type'),
                condition=Q(status='active'),
                name='unique_active_credential_per_installation',
            ),
        ]
        indexes = [
            models.Index(fields=('installation', 'status')),
            models.Index(fields=('credential_type', 'status')),
        ]

    def __str__(self):
        return f'{self.installation} - {self.credential_type} - {self.masked_value}'

    @property
    def organization(self):
        return self.installation.organization

    @property
    def app(self):
        return self.installation.app


class AppCredentialAccessAudit(TimeStampedModel):
    class EventType(models.TextChoices):
        REVEAL = 'reveal', 'Exibicao'

    class Outcome(models.TextChoices):
        SUCCESS = 'success', 'Sucesso'
        DENIED = 'denied', 'Negado'
        NOT_FOUND = 'not_found', 'Nao encontrado'

    organization = models.ForeignKey(
        Organization,
        related_name='credential_access_audits',
        on_delete=models.CASCADE,
    )
    installation = models.ForeignKey(
        OrganizationAppInstallation,
        related_name='access_audits',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    credential = models.ForeignKey(
        OrganizationAppCredential,
        related_name='access_audits',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    app = models.ForeignKey(
        AppCatalog,
        related_name='credential_access_audits',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='credential_access_audits',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    event_type = models.CharField(max_length=16, choices=EventType.choices, default=EventType.REVEAL)
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    reason = models.CharField(max_length=64)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=('organization', 'event_type', 'outcome')),
        ]

    def __str__(self):
        return f'{self.organization.name} - {self.event_type} - {self.outcome}'
