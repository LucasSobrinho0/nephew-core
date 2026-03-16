from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from common.models import PublicIdentifierMixin, TimeStampedModel


class Organization(PublicIdentifierMixin, TimeStampedModel):
    class Segment(models.TextChoices):
        TECHNOLOGY = 'technology', 'Tecnologia'
        CONSULTING = 'consulting', 'Consultoria'
        SERVICES = 'services', 'Servicos'
        OTHER = 'other', 'Outro'

    class TeamSize(models.TextChoices):
        SIZE_1_10 = 'size_1_10', '1 to 10'
        SIZE_11_50 = 'size_11_50', '11 to 50'
        SIZE_51_200 = 'size_51_200', '51 to 200'
        SIZE_200_PLUS = 'size_200_plus', '200 plus'

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    segment = models.CharField(max_length=32, choices=Segment.choices)
    team_size = models.CharField(max_length=32, choices=TeamSize.choices)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_organizations',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class OrganizationMembership(TimeStampedModel):
    class Role(models.TextChoices):
        OWNER = 'owner', 'Proprietario'
        ADMIN = 'admin', 'Administrador'
        USER = 'user', 'Usuario'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='organization_memberships',
        on_delete=models.CASCADE,
    )
    organization = models.ForeignKey(
        Organization,
        related_name='memberships',
        on_delete=models.CASCADE,
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.USER)
    is_active = models.BooleanField(default=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='issued_memberships',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ('organization__name', 'user__full_name', 'user__email')
        constraints = [
            models.UniqueConstraint(fields=('user', 'organization'), name='unique_user_organization_membership'),
            models.UniqueConstraint(
                fields=('organization',),
                condition=Q(role='owner', is_active=True),
                name='unique_active_owner_per_organization',
            ),
        ]

    def __str__(self):
        return f'{self.user} @ {self.organization} ({self.role})'

    @property
    def can_manage_invites(self):
        return self.role in {self.Role.OWNER, self.Role.ADMIN}

    @property
    def can_manage_integrations(self):
        return self.role in {self.Role.OWNER, self.Role.ADMIN}


class OrganizationInvite(PublicIdentifierMixin, TimeStampedModel):
    class TargetRole(models.TextChoices):
        ADMIN = 'admin', 'Administrador'
        USER = 'user', 'Usuario'

    class Status(models.TextChoices):
        AVAILABLE = 'available', 'Disponivel'
        USED = 'used', 'Usado'
        EXPIRED = 'expired', 'Expirado'

    organization = models.ForeignKey(
        Organization,
        related_name='invites',
        on_delete=models.CASCADE,
    )
    code = models.CharField(max_length=12, unique=True)
    target_role = models.CharField(max_length=16, choices=TargetRole.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.AVAILABLE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_organization_invites',
        on_delete=models.PROTECT,
    )
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='used_organization_invites',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=('organization', 'status')),
            models.Index(fields=('code',)),
        ]

    def __str__(self):
        return self.code

    def clean(self):
        prefix_map = {
            self.TargetRole.ADMIN: 'ADM',
            self.TargetRole.USER: 'USR',
        }

        expected_prefix = prefix_map.get(self.target_role)
        if expected_prefix and self.code and not self.code.startswith(f'{expected_prefix} '):
            raise ValidationError({'code': 'O prefixo do codigo de convite nao corresponde ao tipo selecionado.'})
