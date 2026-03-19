from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from common.constants import ACTIVE_ORGANIZATION_SESSION_KEY
from integrations.models import AppCatalog, OrganizationAppInstallation
from organizations.models import Organization, OrganizationMembership


class DispatchFlowModuleTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='dispatch-owner@example.com',
            full_name='Dispatch Owner',
            password='StrongPass123!',
        )
        self.organization = Organization.objects.create(
            name='Dispatch Org',
            slug='dispatch-org',
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
        self.bot_conversa_app = AppCatalog.objects.get(code='bot_conversa')
        self.gmail_app = AppCatalog.objects.get(code='gmail')

    def activate_organization(self):
        session = self.client.session
        session[ACTIVE_ORGANIZATION_SESSION_KEY] = self.organization.id
        session.save()

    def install_app(self, app):
        return OrganizationAppInstallation.objects.create(
            organization=self.organization,
            app=app,
            status=OrganizationAppInstallation.Status.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

    def test_sidebar_shows_dispatch_flow_when_bot_conversa_is_installed(self):
        self.install_app(self.bot_conversa_app)
        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.get(reverse('dashboard:home'))

        self.assertContains(response, reverse('dispatch_flow:index'))

    def test_dispatch_flow_redirects_when_no_supported_app_is_installed(self):
        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.get(reverse('dispatch_flow:index'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('integrations:apps'))

    def test_dispatch_flow_loads_when_gmail_is_installed(self):
        self.install_app(self.gmail_app)
        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.get(reverse('dispatch_flow:index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Disparo de e-mail')
        self.assertNotContains(response, 'Disparo de fluxo')

    def test_dispatch_flow_loads_when_bot_conversa_is_installed(self):
        self.install_app(self.bot_conversa_app)
        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.get(reverse('dispatch_flow:index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Disparo de fluxo')
