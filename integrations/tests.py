from django.db import connection
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from common.constants import ACTIVE_ORGANIZATION_SESSION_KEY
from common.encryption import ENCRYPTED_VALUE_PREFIX
from integrations.models import (
    AppCatalog,
    AppCredentialAccessAudit,
    OrganizationAppCredential,
    OrganizationAppInstallation,
)
from integrations.services import AppCredentialService
from organizations.models import Organization, OrganizationMembership


class IntegrationSecurityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='owner@example.com',
            full_name='Owner User',
            password='StrongPass123!',
        )
        self.admin = User.objects.create_user(
            email='admin@example.com',
            full_name='Admin User',
            password='StrongPass123!',
        )
        self.user = User.objects.create_user(
            email='member@example.com',
            full_name='Member User',
            password='StrongPass123!',
        )
        self.outsider = User.objects.create_user(
            email='outsider@example.com',
            full_name='Outsider User',
            password='StrongPass123!',
        )

        self.organization = Organization.objects.create(
            name='Alpha Org',
            slug='alpha-org',
            segment=Organization.Segment.TECHNOLOGY,
            team_size=Organization.TeamSize.SIZE_1_10,
            created_by=self.owner,
        )
        self.other_organization = Organization.objects.create(
            name='Beta Org',
            slug='beta-org',
            segment=Organization.Segment.SERVICES,
            team_size=Organization.TeamSize.SIZE_11_50,
            created_by=self.outsider,
        )

        OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.organization,
            role=OrganizationMembership.Role.OWNER,
            invited_by=self.owner,
        )
        OrganizationMembership.objects.create(
            user=self.admin,
            organization=self.organization,
            role=OrganizationMembership.Role.ADMIN,
            invited_by=self.owner,
        )
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.organization,
            role=OrganizationMembership.Role.USER,
            invited_by=self.owner,
        )
        OrganizationMembership.objects.create(
            user=self.outsider,
            organization=self.other_organization,
            role=OrganizationMembership.Role.OWNER,
            invited_by=self.outsider,
        )

        self.apollo = AppCatalog.objects.get(code='apollo')
        self.hubspot = AppCatalog.objects.get(code='hubspot')

        self.installation = OrganizationAppInstallation.objects.create(
            organization=self.organization,
            app=self.apollo,
            status=OrganizationAppInstallation.Status.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.other_installation = OrganizationAppInstallation.objects.create(
            organization=self.other_organization,
            app=self.apollo,
            status=OrganizationAppInstallation.Status.ACTIVE,
            created_by=self.outsider,
            updated_by=self.outsider,
        )

    def activate_organization(self, organization):
        session = self.client.session
        session[ACTIVE_ORGANIZATION_SESSION_KEY] = organization.id
        session.save()

    def create_api_key(self, api_key='sk_live_TESTKEY9876'):
        credential, _ = AppCredentialService.save_api_key(
            user=self.owner,
            organization=self.organization,
            installation=self.installation,
            api_key=api_key,
        )
        return credential

    def test_api_keys_page_is_restricted_to_organization_managers(self):
        self.client.force_login(self.user)
        self.activate_organization(self.organization)

        response = self.client.get(reverse('integrations:api_keys'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], reverse('dashboard:home'))

    def test_api_keys_page_does_not_expose_plain_secret_in_initial_html(self):
        credential = self.create_api_key()
        self.client.force_login(self.owner)
        self.activate_organization(self.organization)

        response = self.client.get(reverse('integrations:api_keys'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, credential.secret_value, html=False)
        self.assertContains(response, credential.masked_value)
        self.assertIn('no-store', response.headers.get('Cache-Control', ''))

    def test_api_keys_page_lists_only_installed_apps_for_active_organization(self):
        self.client.force_login(self.owner)
        self.activate_organization(self.organization)

        response = self.client.get(reverse('integrations:api_keys'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.apollo.name)
        self.assertContains(response, str(self.installation.public_id))
        self.assertNotContains(response, self.hubspot.name)
        self.assertNotContains(response, 'Install required')

    def test_api_key_is_encrypted_at_rest(self):
        credential = self.create_api_key()

        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT secret_value FROM integrations_organizationappcredential WHERE id = %s',
                [credential.id],
            )
            encrypted_secret = cursor.fetchone()[0]

        self.assertTrue(encrypted_secret.startswith(ENCRYPTED_VALUE_PREFIX))
        self.assertNotEqual(encrypted_secret, 'sk_live_TESTKEY9876')
        self.assertEqual(
            OrganizationAppCredential.objects.get(pk=credential.pk).secret_value,
            'sk_live_TESTKEY9876',
        )

    def test_user_role_cannot_reveal_api_key_even_with_direct_endpoint_access(self):
        self.create_api_key()
        self.client.force_login(self.user)
        self.activate_organization(self.organization)

        response = self.client.post(
            reverse('integrations:reveal_api_key', args=[self.installation.public_id]),
            {'confirmation_word': 'mostrar'},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()['detail'],
            'Voce nao tem permissao para visualizar chaves de API.',
        )

    def test_reveal_api_key_requires_exact_confirmation_word(self):
        self.create_api_key()
        self.client.force_login(self.owner)
        self.activate_organization(self.organization)

        response = self.client.post(
            reverse('integrations:reveal_api_key', args=[self.installation.public_id]),
            {'confirmation_word': 'MOSTRAR'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['detail'], 'A palavra de confirmacao esta invalida.')
        self.assertFalse('api_key' in response.json())
        self.assertTrue(
            AppCredentialAccessAudit.objects.filter(
                organization=self.organization,
                actor=self.owner,
                outcome=AppCredentialAccessAudit.Outcome.DENIED,
                reason='invalid_confirmation_word',
            ).exists()
        )

    def test_reveal_api_key_returns_secret_after_backend_confirmation(self):
        self.create_api_key()
        self.client.force_login(self.admin)
        self.activate_organization(self.organization)

        response = self.client.post(
            reverse('integrations:reveal_api_key', args=[self.installation.public_id]),
            {'confirmation_word': 'mostrar'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['api_key'], 'sk_live_TESTKEY9876')
        self.assertIn('no-store', response.headers.get('Cache-Control', ''))
        self.assertTrue(
            AppCredentialAccessAudit.objects.filter(
                organization=self.organization,
                actor=self.admin,
                outcome=AppCredentialAccessAudit.Outcome.SUCCESS,
                reason='confirmation_accepted',
            ).exists()
        )

    def test_reveal_api_key_returns_404_for_cross_tenant_installation_lookup(self):
        self.create_api_key()
        AppCredentialService.save_api_key(
            user=self.outsider,
            organization=self.other_organization,
            installation=self.other_installation,
            api_key='sk_live_OTHERTENANT9999',
        )
        self.client.force_login(self.owner)
        self.activate_organization(self.organization)

        response = self.client.post(
            reverse('integrations:reveal_api_key', args=[self.other_installation.public_id]),
            {'confirmation_word': 'mostrar'},
        )

        self.assertEqual(response.status_code, 404)

    def test_install_app_creates_record_only_for_active_organization(self):
        self.client.force_login(self.owner)
        self.activate_organization(self.organization)

        response = self.client.post(
            reverse('integrations:install_app'),
            {
                'app_public_id': self.hubspot.public_id,
                'next': reverse('integrations:apps'),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            OrganizationAppInstallation.objects.filter(
                organization=self.organization,
                app=self.hubspot,
                status=OrganizationAppInstallation.Status.ACTIVE,
            ).exists()
        )
        self.assertFalse(
            OrganizationAppInstallation.objects.filter(
                organization=self.other_organization,
                app=self.hubspot,
            ).exists()
        )
