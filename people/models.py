from django.conf import settings
from django.db import models

from companies.models import Company
from common.encryption import build_email_lookup, normalize_email_address
from common.fields import EncryptedTextField
from common.models import PublicIdentifierMixin, TimeStampedModel
from common.phone import format_phone_display, normalize_phone
from organizations.models import Organization


class PersonQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def for_organization(self, organization):
        return self.filter(organization=organization)

    def with_related_objects(self):
        return self.select_related('organization', 'created_by', 'updated_by')


class Person(PublicIdentifierMixin, TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        related_name='persons',
        on_delete=models.CASCADE,
    )
    bot_conversa_id = models.CharField(max_length=128, null=True, blank=True, db_index=True)
    hubspot_contact_id = models.CharField(max_length=128, blank=True, default='', db_index=True)
    company = models.ForeignKey(
        Company,
        related_name='persons',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    phone = models.CharField(max_length=32)
    normalized_phone = models.CharField(max_length=16, editable=False, db_index=True)
    email = EncryptedTextField(blank=True, default='')
    email_lookup = models.CharField(max_length=64, blank=True, default='', db_index=True)
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_persons',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='updated_persons',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    objects = PersonQuerySet.as_manager()

    class Meta:
        ordering = ('first_name', 'last_name', 'normalized_phone')
        constraints = [
            models.UniqueConstraint(
                fields=('organization', 'normalized_phone'),
                name='unique_person_phone_per_organization',
            ),
            models.UniqueConstraint(
                fields=('organization', 'email_lookup'),
                condition=~models.Q(email_lookup=''),
                name='unique_person_email_per_organization',
            ),
            models.UniqueConstraint(
                fields=('organization', 'bot_conversa_id'),
                condition=models.Q(bot_conversa_id__isnull=False),
                name='unique_person_bot_conversa_id_per_organization',
            ),
            models.UniqueConstraint(
                fields=('organization', 'hubspot_contact_id'),
                condition=~models.Q(hubspot_contact_id=''),
                name='unique_person_hubspot_contact_id_per_organization',
            ),
        ]

    def save(self, *args, **kwargs):
        self.bot_conversa_id = (self.bot_conversa_id or '').strip() or None
        self.hubspot_contact_id = (self.hubspot_contact_id or '').strip()
        self.normalized_phone = normalize_phone(self.phone)
        self.phone = format_phone_display(self.normalized_phone)
        normalized_email = normalize_email_address(self.email) if self.email else ''
        self.email = normalized_email
        self.email_lookup = build_email_lookup(normalized_email) if normalized_email else ''
        self.first_name = self.first_name.strip()
        self.last_name = self.last_name.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.full_name} ({self.phone})'

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()
