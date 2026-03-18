from django.test import TestCase

from accounts.models import User
from companies.services import CompanyService
from organizations.models import Organization


class CompanyServiceTests(TestCase):
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
