from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from common.constants import ACTIVE_ORGANIZATION_SESSION_KEY
from companies.services import CompanyService
from hubspot_integration.models import HubSpotDeal, HubSpotPipelineCache
from integrations.models import AppCatalog, OrganizationAppInstallation
from integrations.services import AppCredentialService
from organizations.models import Organization, OrganizationMembership
from people.services import PersonService


class HubSpotModuleTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='hubspot-owner@example.com',
            full_name='HubSpot Owner',
            password='StrongPass123!',
        )
        self.organization = Organization.objects.create(
            name='HubSpot Org',
            slug='hubspot-org',
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
        self.hubspot_app = AppCatalog.objects.get(code='hubspot')
        self.installation = OrganizationAppInstallation.objects.create(
            organization=self.organization,
            app=self.hubspot_app,
            status=OrganizationAppInstallation.Status.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        AppCredentialService.save_api_key(
            user=self.owner,
            organization=self.organization,
            installation=self.installation,
            api_key='hubspot-private-token',
        )
        self.company = CompanyService.create_company(
            user=self.owner,
            organization=self.organization,
            name='ACME',
            website='https://acme.test',
            phone='+55 11 4000-0000',
            hubspot_company_id='company-1',
        )
        self.person = PersonService.create_person(
            user=self.owner,
            organization=self.organization,
            first_name='Ana',
            last_name='Costa',
            email='ana@acme.test',
            phone='+55 11 99999-0000',
            company=self.company,
            hubspot_contact_id='contact-1',
        )
        self.pipeline = HubSpotPipelineCache.objects.create(
            organization=self.organization,
            installation=self.installation,
            hubspot_pipeline_id='pipeline-1',
            name='Pipeline Comercial',
            object_type='deals',
            raw_payload={'id': 'pipeline-1', 'stages': [{'id': 'appointmentscheduled'}]},
            last_synced_at=self.installation.created_at,
        )

    def activate_organization(self):
        session = self.client.session
        session[ACTIVE_ORGANIZATION_SESSION_KEY] = self.organization.id
        session.save()

    def test_sidebar_shows_hubspot_when_installed(self):
        self.client.force_login(self.owner)
        self.activate_organization()
        response = self.client.get(reverse('dashboard:home'))
        self.assertContains(response, reverse('hubspot_integration:dashboard'))

    @patch('hubspot_integration.client.HubSpotClient.create_deal')
    def test_create_deal_persists_remote_id(self, create_deal_mock):
        create_deal_mock.return_value = {'hubspot_deal_id': 'deal-1', 'raw_payload': {'id': 'deal-1'}}
        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.post(
            reverse('hubspot_integration:create_deal'),
            {
                'company_public_id': self.company.public_id,
                'pipeline_public_id': self.pipeline.public_id,
                'stage_id': 'appointmentscheduled',
                'deal_name': 'ACME - Diagnóstico',
                'amount': '10000',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(HubSpotDeal.objects.filter(hubspot_deal_id='deal-1').exists())

    @patch('hubspot_integration.client.HubSpotClient.create_deal')
    @patch('hubspot_integration.client.HubSpotClient.create_or_get_company')
    def test_create_company_with_business_creates_company_and_deal(self, create_company_mock, create_deal_mock):
        create_company_mock.return_value = {
            'hubspot_company_id': 'company-99',
            'raw_payload': {'id': 'company-99'},
        }
        create_deal_mock.return_value = {'hubspot_deal_id': 'deal-99', 'raw_payload': {'id': 'deal-99'}}
        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.post(
            reverse('hubspot_integration:create_company'),
            {
                'name': 'Beta',
                'website': 'https://beta.test',
                'phone': '+55 11 4000-1111',
                'email': '',
                'segment': '',
                'employee_count': '',
                'create_deal_now': 'on',
                'pipeline_public_id': self.pipeline.public_id,
                'stage_id': 'appointmentscheduled',
                'deal_name': 'Beta - Novo negocio',
                'amount': '20000',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(HubSpotDeal.objects.filter(hubspot_deal_id='deal-99', name='Beta - Novo negocio').exists())

    @patch('hubspot_integration.client.HubSpotClient.associate_contact_to_deal')
    @patch('hubspot_integration.client.HubSpotClient.create_or_get_contact')
    def test_create_person_with_business_links_person_to_deal(self, create_contact_mock, associate_contact_mock):
        create_contact_mock.return_value = {
            'hubspot_contact_id': 'contact-99',
            'raw_payload': {'id': 'contact-99'},
        }
        associate_contact_mock.return_value = {}
        deal = HubSpotDeal.objects.create(
            organization=self.organization,
            installation=self.installation,
            company=self.company,
            pipeline=self.pipeline,
            hubspot_deal_id='deal-55',
            name='ACME - Expansao',
            amount='5000',
            stage_id='appointmentscheduled',
            created_by=self.owner,
            updated_by=self.owner,
        )

        self.client.force_login(self.owner)
        self.activate_organization()
        response = self.client.post(
            reverse('hubspot_integration:create_person'),
            {
                'first_name': 'Bruno',
                'last_name': 'Sales',
                'email': 'bruno@acme.test',
                'phone': '+55 11 98888-7777',
                'company_public_id': self.company.public_id,
                'deal_public_id': deal.public_id,
            },
        )

        self.assertEqual(response.status_code, 302)
        person = self.organization.persons.get(first_name='Bruno', last_name='Sales')
        self.assertEqual(person.hubspot_contact_id, 'contact-99')
        self.assertTrue(deal.persons.filter(pk=person.pk).exists())
        associate_contact_mock.assert_called_once_with(contact_id='contact-99', deal_id='deal-55')

    def test_deal_search_returns_local_business_results(self):
        deal = HubSpotDeal.objects.create(
            organization=self.organization,
            installation=self.installation,
            company=self.company,
            pipeline=self.pipeline,
            hubspot_deal_id='deal-22',
            name='ACME - Renovacao',
            amount='3000',
            stage_id='appointmentscheduled',
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.get(reverse('hubspot_integration:deal_search'), {'q': 'Renova'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['results'][0]['value'], str(deal.public_id))

    @patch('hubspot_integration.services.HubSpotRemoteAssociationService.build_company_summaries')
    def test_local_companies_list_does_not_query_hubspot_by_default(self, build_company_summaries_mock):
        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.get(reverse('hubspot_integration:companies'), {'load_local': '1'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nao verificado')
        build_company_summaries_mock.assert_not_called()

    @patch('hubspot_integration.services.HubSpotRemoteAssociationService.build_company_summaries')
    def test_local_companies_list_queries_hubspot_when_requested(self, build_company_summaries_mock):
        build_company_summaries_mock.return_value = {
            self.company.id: {
                'was_resolved': True,
                'has_remote_deal': True,
                'remote_deal_count': 2,
            }
        }
        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.get(
            reverse('hubspot_integration:companies'),
            {'load_local': '1', 'check_remote_status': '1'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '2 negocio(s)')
        build_company_summaries_mock.assert_called_once()

    @patch('hubspot_integration.services.HubSpotRemoteAssociationService.build_person_summaries')
    def test_local_people_list_does_not_query_hubspot_by_default(self, build_person_summaries_mock):
        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.get(reverse('hubspot_integration:people'), {'load_local': '1'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nao verificado')
        build_person_summaries_mock.assert_not_called()

    @patch('hubspot_integration.services.HubSpotRemoteAssociationService.build_person_summaries')
    def test_local_people_list_queries_hubspot_when_requested(self, build_person_summaries_mock):
        build_person_summaries_mock.return_value = {
            self.person.id: {
                'was_resolved': True,
                'has_remote_deal': False,
                'remote_deal_count': 0,
            }
        }
        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.get(
            reverse('hubspot_integration:people'),
            {'load_local': '1', 'check_remote_status': '1'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sincronizada')
        build_person_summaries_mock.assert_called_once()
