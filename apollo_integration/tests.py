from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from apollo_integration.client import ApolloClient
from apollo_integration.models import ApolloCompanySyncLog
from apollo_integration.services import ApolloCompanyService, ApolloInstallationService, ApolloPersonService
from common.constants import ACTIVE_ORGANIZATION_SESSION_KEY
from companies.models import Company
from integrations.models import AppCatalog, OrganizationAppInstallation
from integrations.services import AppCredentialService
from organizations.models import Organization, OrganizationMembership
from people.models import Person


class FakeApolloClient:
    def __init__(self):
        self.last_search_payload = None
        self.last_people_payload = None

    def search_organizations(self, *, payload):
        self.last_search_payload = payload
        return {
            'organizations': [
                {
                    'apollo_company_id': 'apollo-1',
                    'name': 'Apollo One',
                    'website': 'https://acme.io',
                    'segment': 'Software',
                    'employee_count': 180,
                    'email': 'info@acme.io',
                    'phone': '+55 11 4000-0000',
                    'raw_payload': {'id': 'apollo-1'},
                },
                {
                    'apollo_company_id': 'apollo-2',
                    'name': 'Apollo Two',
                    'website': 'https://other.example',
                    'segment': 'Services',
                    'employee_count': 8,
                    'email': '',
                    'phone': '',
                    'raw_payload': {'id': 'apollo-2'},
                },
            ],
            'pagination': {'total_entries': 2, 'total_pages': 1},
        }

    def search_people(self, *, payload):
        self.last_people_payload = payload
        return {
            'people': [
                {
                    'apollo_person_id': 'apollo-person-1',
                    'first_name': 'Carla',
                    'last_name': '',
                    'last_name_obfuscated': 'So***a',
                    'title': 'Financial Supervisor',
                    'has_email': True,
                    'has_direct_phone': 'Yes',
                    'last_refreshed_at': '2025-11-10T08:39:18.742+00:00',
                    'organization_name': 'Apollo One',
                    'organization_website': 'https://acme.io',
                    'organization_apollo_company_id': 'apollo-1',
                    'email': '',
                    'phone': '',
                    'raw_payload': {'id': 'apollo-person-1'},
                }
            ],
            'pagination': {'total_entries': 1, 'total_pages': 1},
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
    def test_remote_company_list_builds_apollo_payload_from_filters(self, build_client_mock):
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
    def test_bulk_import_company_view_uses_current_query_and_persists_company(self, build_client_mock):
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

    @patch('apollo_integration.services.ApolloInstallationService.build_client')
    def test_remote_people_list_builds_apollo_payload_from_company_and_person_filters(self, build_client_mock):
        fake_client = FakeApolloClient()
        build_client_mock.return_value = fake_client
        company = Company.objects.create(
            organization=self.organization,
            name='Apollo One',
            website='https://acme.io',
            created_by=self.owner,
            updated_by=self.owner,
        )

        response = ApolloPersonService.list_remote_people(
            organization=self.organization,
            filters={
                'company_public_id': str(company.public_id),
                'person_titles': ['financial supervisor'],
                'q_keywords': 'Carla',
                'contact_email_status': 'verified',
                'per_page': 25,
            },
        )

        self.assertEqual(response['pagination']['total_entries'], 1)
        self.assertEqual(len(response['people']), 1)
        self.assertEqual(fake_client.last_people_payload['q_organization_domains_list'], ['acme.io'])
        self.assertEqual(fake_client.last_people_payload['person_titles'], ['financial supervisor'])
        self.assertEqual(fake_client.last_people_payload['q_keywords'], 'Carla')
        self.assertEqual(fake_client.last_people_payload['contact_email_status'], 'verified')

    def test_import_remote_people_persists_apollo_person_id_without_phone(self):
        company = Company.objects.create(
            organization=self.organization,
            name='Apollo One',
            apollo_company_id='apollo-1',
            website='https://acme.io',
            created_by=self.owner,
            updated_by=self.owner,
        )

        ApolloPersonService.import_remote_people(
            user=self.owner,
            organization=self.organization,
            remote_people=[
                {
                    'apollo_person_id': 'apollo-person-1',
                    'first_name': 'Carla',
                    'last_name': '',
                    'last_name_obfuscated': 'So***a',
                    'title': 'Financial Supervisor',
                    'organization_name': 'Apollo One',
                    'organization_website': 'https://acme.io',
                    'organization_apollo_company_id': 'apollo-1',
                    'email': '',
                    'phone': '',
                }
            ],
        )

        person = Person.objects.get(organization=self.organization, apollo_person_id='apollo-person-1')
        self.assertEqual(person.first_name, 'Carla')
        self.assertEqual(person.last_name, 'So***a')
        self.assertEqual(person.company_id, company.id)
        self.assertEqual(person.phone, '')

    @patch('apollo_integration.services.ApolloInstallationService.build_client')
    def test_people_page_renders_remote_people(self, build_client_mock):
        build_client_mock.return_value = FakeApolloClient()
        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.get(
            reverse('apollo_integration:people'),
            {
                'q_keywords': 'Carla',
                'per_page': '25',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Carla')
        self.assertContains(response, 'Financial Supervisor')

    @patch('apollo_integration.services.ApolloInstallationService.build_client')
    def test_bulk_import_people_view_persists_person(self, build_client_mock):
        build_client_mock.return_value = FakeApolloClient()
        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.post(
            reverse('apollo_integration:import_people_bulk'),
            {
                'apollo_person_ids': ['apollo-person-1'],
                'current_query': 'search=1&q_keywords=Carla&per_page=25',
            },
        )

        self.assertEqual(response.status_code, 302)
        person = Person.objects.get(organization=self.organization, apollo_person_id='apollo-person-1')
        self.assertEqual(person.first_name, 'Carla')

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

    def test_client_normalizes_person_payload(self):
        normalized = ApolloClient._normalize_person_payload(
            {
                'id': 'apollo-person-9',
                'first_name': 'Joao',
                'last_name_obfuscated': 'Si***a',
                'title': 'IT Manager',
                'has_email': True,
                'has_direct_phone': 'Yes',
                'organization': {
                    'id': 'apollo-company-9',
                    'name': 'Tech Co',
                    'website_url': 'https://tech.example',
                },
            }
        )

        self.assertEqual(normalized['apollo_person_id'], 'apollo-person-9')
        self.assertEqual(normalized['organization_apollo_company_id'], 'apollo-company-9')
        self.assertEqual(normalized['organization_name'], 'Tech Co')
