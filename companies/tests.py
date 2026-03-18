from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from common.constants import ACTIVE_ORGANIZATION_SESSION_KEY
from companies.services import CompanyService
from integrations.models import AppCatalog, OrganizationAppInstallation
from organizations.models import Organization, OrganizationMembership


class CompanyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='company-owner@example.com',
            full_name='Company Owner',
            password='StrongPass123!',
        )
        self.organization = Organization.objects.create(
            name='Companies Org',
            slug='companies-org',
            segment=Organization.Segment.TECHNOLOGY,
            team_size=Organization.TeamSize.SIZE_1_10,
            created_by=self.user,
        )
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.organization,
            role=OrganizationMembership.Role.OWNER,
            invited_by=self.user,
        )

    def activate_organization(self):
        session = self.client.session
        session[ACTIVE_ORGANIZATION_SESSION_KEY] = self.organization.id
        session.save()

    def test_create_company_normalizes_phone_and_external_ids(self):
        company = CompanyService.create_company(
            user=self.user,
            organization=self.organization,
            name='ACME',
            website='https://acme.test',
            email=' SALES@acme.test ',
            phone='(11) 4000-0000',
            apollo_company_id=' ap-123 ',
            hubspot_company_id=' 123 ',
        )

        self.assertEqual(company.apollo_company_id, 'ap-123')
        self.assertEqual(company.hubspot_company_id, '123')
        self.assertEqual(company.email, 'sales@acme.test')
        self.assertTrue(company.normalized_phone)

    def test_companies_page_hides_optional_external_fields_when_apps_are_not_installed(self):
        self.client.force_login(self.user)
        self.activate_organization()

        response = self.client.get(reverse('companies:index'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'ID da empresa no HubSpot')
        self.assertNotContains(response, 'ID da empresa no Apollo')

    def test_companies_page_shows_optional_external_fields_when_apps_are_installed(self):
        self.client.force_login(self.user)
        self.activate_organization()

        for app_code in ('hubspot', 'apollo'):
            app = AppCatalog.objects.get(code=app_code)
            OrganizationAppInstallation.objects.create(
                organization=self.organization,
                app=app,
                status=OrganizationAppInstallation.Status.ACTIVE,
                created_by=self.user,
                updated_by=self.user,
            )

        response = self.client.get(reverse('companies:index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ID da empresa no HubSpot')
        self.assertContains(response, 'ID da empresa no Apollo')

    def test_sidebar_lists_companies_before_people(self):
        self.client.force_login(self.user)
        self.activate_organization()

        response = self.client.get(reverse('dashboard:home'))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertLess(content.index('Empresas'), content.index('Pessoas'))
