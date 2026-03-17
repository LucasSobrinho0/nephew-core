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
                'deal_name': 'ACME - Diagnóstico',
                'amount': '10000',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(HubSpotDeal.objects.filter(hubspot_deal_id='deal-1').exists())
