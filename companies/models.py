from django.conf import settings
from django.db import models

from common.models import PublicIdentifierMixin, TimeStampedModel
from common.phone import format_phone_display, normalize_phone
from organizations.models import Organization


class CompanyQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def for_organization(self, organization):
        return self.filter(organization=organization)

    def with_related_objects(self):
        return self.select_related('organization', 'created_by', 'updated_by')


class Company(PublicIdentifierMixin, TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        related_name='companies',
        on_delete=models.CASCADE,
    )
    apollo_company_id = models.CharField(max_length=128, blank=True, default='', db_index=True)
    hubspot_company_id = models.CharField(max_length=128, blank=True, default='', db_index=True)
    name = models.CharField(max_length=255)
    website = models.URLField(max_length=255, blank=True)
    email = models.EmailField(max_length=254, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    segment = models.CharField(max_length=255, blank=True, default='')
    employee_count = models.PositiveIntegerField(null=True, blank=True)
    normalized_phone = models.CharField(max_length=16, editable=False, db_index=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_companies',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='updated_companies',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    objects = CompanyQuerySet.as_manager()

    class Meta:
        ordering = ('name', 'website')
        constraints = [
            models.UniqueConstraint(
                fields=('organization', 'apollo_company_id'),
                condition=~models.Q(apollo_company_id=''),
                name='unique_company_apollo_id_per_organization',
            ),
            models.UniqueConstraint(
                fields=('organization', 'hubspot_company_id'),
                condition=~models.Q(hubspot_company_id=''),
                name='unique_company_hubspot_id_per_organization',
            ),
        ]

    def save(self, *args, **kwargs):
        self.apollo_company_id = (self.apollo_company_id or '').strip()
        self.hubspot_company_id = (self.hubspot_company_id or '').strip()
        self.name = self.name.strip()
        self.website = (self.website or '').strip()
        self.email = (self.email or '').strip().lower()
        self.segment = (self.segment or '').strip()
        normalized_phone = normalize_phone(self.phone) if self.phone else ''
        self.normalized_phone = normalized_phone
        self.phone = format_phone_display(normalized_phone) if normalized_phone else ''
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
