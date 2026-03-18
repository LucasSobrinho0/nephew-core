from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from apollo_integration.client import ApolloClient
from apollo_integration.models import ApolloCompanySyncLog
from apollo_integration.services import ApolloCompanyService, ApolloInstallationService
from common.constants import ACTIVE_ORGANIZATION_SESSION_KEY
from companies.models import Company
from integrations.models import AppCatalog, OrganizationAppInstallation
from integrations.services import AppCredentialService
from organizations.models import Organization, OrganizationMembership


class FakeApolloClient:
    def __init__(self):
        self.last_search_payload = None

    def search_organizations(self, *, payload):
        self.last_search_payload = payload
        return {
            'organizations': [
                {
                    'id': 'apollo-1',
                    'organization': {
                        'id': 'apollo-1',
                        'name': 'Apollo One',
                        'website_url': 'https://acme.io',
                        'industry': 'Software',
                        'estimated_num_employees': 180,
                        'primary_email': 'INFO@ACME.IO',
                        'primary_phone': '+55 11 4000-0000',
                    },
                },
                {
                    'id': 'apollo-2',
                    'organization': {
                        'id': 'apollo-2',
                        'name': 'Apollo Two',
                        'website_url': 'https://other.example',
                        'industry': 'Services',
                        'estimated_num_employees': 8,
                    },
                },
            ],
            'pagination': {'total_entries': 2},
            'raw_payload': {'total_entries': 2},
        }

    def get_usage_stats(self):
        return {
            'credits_used': 12,
            'credits_remaining': 188,
            'limits': {
                'per_minute': 60,
                'per_hour': 1000,
                'per_day': 10000,
            },
        }


class ApolloModuleTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='apollo-owner@example.com',
            full_name='Apollo Owner',
            password='StrongPass123!',
        )
        self.user = User.objects.create_user(
            email='apollo-user@example.com',
            full_name='Apollo User',
            password='StrongPass123!',
        )
        self.organization = Organization.objects.create(
            name='Apollo Org',
            slug='apollo-org',
            segment=Organization.Segment.TECHNOLOGY,
            team_size=Organization.TeamSize.SIZE_1_10,
            created_by=self.owner,
        )
        OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.organization,
            role=OrganizationMembership.Role.OWNER,
            invited_by=self.owner,
        )
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.organization,
            role=OrganizationMembership.Role.USER,
            invited_by=self.owner,
        )

        self.apollo_app = AppCatalog.objects.get(code='apollo')
        self.installation = OrganizationAppInstallation.objects.create(
            organization=self.organization,
            app=self.apollo_app,
            status=OrganizationAppInstallation.Status.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        AppCredentialService.save_api_key(
            user=self.owner,
            organization=self.organization,
            installation=self.installation,
            api_key='apollo-private-token',
        )

    def activate_organization(self):
        session = self.client.session
        session[ACTIVE_ORGANIZATION_SESSION_KEY] = self.organization.id
        session.save()

    def test_sidebar_lists_apollo_when_installed(self):
        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.get(reverse('dashboard:home'))

        self.assertContains(response, 'Apollo')
        self.assertContains(response, reverse('apollo_integration:dashboard'))

    @patch('apollo_integration.services.ApolloInstallationService.build_client')
    def test_dashboard_shows_usage_snapshot(self, build_client_mock):
        build_client_mock.return_value = FakeApolloClient()
        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.get(reverse('apollo_integration:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '12')
        self.assertContains(response, '188')
        self.assertContains(response, '60')

    @patch('apollo_integration.services.ApolloInstallationService.build_client')
    def test_remote_list_builds_apollo_payload_from_filters(self, build_client_mock):
        fake_client = FakeApolloClient()
        build_client_mock.return_value = fake_client

        response = ApolloCompanyService.list_remote_companies(
            organization=self.organization,
            filters={
                'q_organization_name': 'Apollo',
                'q_organization_domains': ['acme.io'],
                'organization_locations': ['Brazil'],
                'organization_industries': ['Software'],
                'organization_num_employees_ranges': ['101,200'],
                'per_page': 25,
            },
        )

        self.assertEqual(response['pagination']['total_entries'], 2)
        self.assertEqual(len(response['companies']), 2)
        self.assertEqual(fake_client.last_search_payload['q_organization_name'], 'Apollo')
        self.assertEqual(fake_client.last_search_payload['q_organization_domains_list'], ['acme.io'])
        self.assertEqual(fake_client.last_search_payload['organization_locations'], ['Brazil'])
        self.assertEqual(fake_client.last_search_payload['organization_industries'], ['Software'])
        self.assertEqual(fake_client.last_search_payload['organization_num_employees_ranges'], ['101,200'])

    def test_import_remote_companies_persists_apollo_fields(self):
        ApolloCompanyService.import_remote_companies(
            user=self.owner,
            organization=self.organization,
            remote_companies=[
                {
                    'apollo_company_id': 'apollo-1',
                    'name': 'Apollo One',
                    'website': 'https://acme.io',
                    'email': 'info@acme.io',
                    'phone': '+55 11 4000-0000',
                    'segment': 'Software',
                    'employee_count': 180,
                    'raw_payload': {'id': 'apollo-1'},
                }
            ],
        )

        company = Company.objects.get(organization=self.organization, apollo_company_id='apollo-1')
        self.assertEqual(company.name, 'Apollo One')
        self.assertEqual(company.website, 'https://acme.io')
        self.assertEqual(company.segment, 'Software')
        self.assertEqual(company.employee_count, 180)
        self.assertEqual(company.email, 'info@acme.io')
        self.assertEqual(company.phone, '+55 11 4000-0000')
        self.assertTrue(
            ApolloCompanySyncLog.objects.filter(
                organization=self.organization,
                company=company,
                action=ApolloCompanySyncLog.Action.IMPORT,
                outcome=ApolloCompanySyncLog.Outcome.SUCCESS,
            ).exists()
        )

    @patch('apollo_integration.services.ApolloInstallationService.build_client')
    def test_bulk_import_view_uses_current_query_and_persists_company(self, build_client_mock):
        build_client_mock.return_value = FakeApolloClient()
        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.post(
            reverse('apollo_integration:import_companies_bulk'),
            {
                'apollo_company_ids': ['apollo-1'],
                'current_query': 'search=1&per_page=25',
            },
        )

        self.assertEqual(response.status_code, 302)
        company = Company.objects.get(organization=self.organization, apollo_company_id='apollo-1')
        self.assertEqual(company.name, 'Apollo One')

    def test_user_role_cannot_save_remote_companies(self):
        self.client.force_login(self.user)
        self.activate_organization()

        response = self.client.post(
            reverse('apollo_integration:import_companies_bulk'),
            {
                'apollo_company_ids': ['apollo-1'],
                'current_query': 'search=1&per_page=25',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], reverse('apollo_integration:dashboard'))
        self.assertFalse(Company.objects.filter(organization=self.organization, apollo_company_id='apollo-1').exists())

    def test_installation_service_uses_saved_api_key(self):
        installation, api_key = ApolloInstallationService.get_api_key(organization=self.organization)

        self.assertEqual(installation.pk, self.installation.pk)
        self.assertEqual(api_key, 'apollo-private-token')

    @patch('apollo_integration.services.ApolloInstallationService.build_client')
    def test_companies_page_loads_remote_results_when_query_has_filters_without_search_flag(self, build_client_mock):
        build_client_mock.return_value = FakeApolloClient()
        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.get(
            reverse('apollo_integration:companies'),
            {
                'q_organization_name': 'Apollo',
                'per_page': '25',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Apollo One')

    def test_client_extracts_companies_key_shape(self):
        response_payload = {
            'companies': [
                {
                    'id': 'apollo-3',
                    'name': 'Apollo Three',
                    'website_url': 'https://third.example',
                    'industry': 'Energy',
                    'estimated_num_employees': 24,
                }
            ],
            'pagination': {'total_entries': 1},
        }

        extracted = ApolloClient._extract_organization_items(response_payload)
        normalized = ApolloClient._normalize_company_payload(extracted[0])

        self.assertEqual(len(extracted), 1)
        self.assertEqual(normalized['name'], 'Apollo Three')
        self.assertEqual(ApolloClient._extract_pagination(response_payload)['total_entries'], 1)
