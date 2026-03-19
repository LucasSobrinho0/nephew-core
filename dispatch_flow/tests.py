from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from bot_conversa.models import BotConversaFlowCache
from common.constants import ACTIVE_ORGANIZATION_SESSION_KEY
from gmail_integration.models import GmailTemplate
from integrations.models import AppCatalog, OrganizationAppInstallation
from organizations.models import Organization, OrganizationMembership
from people.models import Person


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
        self.assertContains(response, 'Central unificada de envio')
        self.assertContains(response, 'Enviar por Gmail')
        self.assertNotContains(response, 'Enviar por WhatsApp')

    def test_dispatch_flow_loads_when_bot_conversa_is_installed(self):
        self.install_app(self.bot_conversa_app)
        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.get(reverse('dispatch_flow:index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Central unificada de envio')
        self.assertContains(response, 'Enviar por WhatsApp')

    def test_dispatch_flow_preserves_selected_people_when_channel_contact_data_is_missing(self):
        self.install_app(self.gmail_app)
        bot_installation = self.install_app(self.bot_conversa_app)
        template = GmailTemplate.objects.create(
            organization=self.organization,
            name='Primeiro contato',
            subject='Ola',
            body='Mensagem',
            is_active=True,
            created_by=self.owner,
            updated_by=self.owner,
        )
        flow = BotConversaFlowCache.objects.create(
            organization=self.organization,
            installation=bot_installation,
            external_flow_id='flow-001',
            name='Fluxo principal',
            status=BotConversaFlowCache.Status.ACTIVE,
            last_synced_at=self.organization.created_at,
        )
        person_without_email = Person.objects.create(
            organization=self.organization,
            first_name='Ana',
            last_name='Sem Email',
            phone='+5511999999999',
            created_by=self.owner,
            updated_by=self.owner,
        )
        person_without_phone = Person.objects.create(
            organization=self.organization,
            first_name='Bruno',
            last_name='Sem Telefone',
            email='bruno@example.com',
            created_by=self.owner,
            updated_by=self.owner,
        )

        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.post(
            reverse('dispatch_flow:create_dispatch'),
            {
                'audience_filter': 'all',
                'person_public_ids': [
                    str(person_without_email.public_id),
                    str(person_without_phone.public_id),
                ],
                'send_bot_conversa': 'on',
                'send_gmail': 'on',
                'flow_public_id': str(flow.public_id),
                'gmail_template_public_id': str(template.public_id),
                'bot_min_delay_seconds': '0',
                'bot_max_delay_seconds': '0',
                'gmail_min_delay_seconds': '0',
                'gmail_max_delay_seconds': '0',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ana Sem Email')
        self.assertContains(response, 'Bruno Sem Telefone')
        self.assertContains(response, 'nao possuem e-mail para Gmail')
        self.assertContains(response, 'nao possuem telefone para WhatsApp')
        self.assertContains(response, f'value="{person_without_email.public_id}"', html=False)
        self.assertContains(response, f'value="{person_without_phone.public_id}"', html=False)
        self.assertContains(
            response,
            f'name="person_public_ids" value="{person_without_email.public_id}" data-checkbox-group="dispatch-flow-selection" checked',
            html=False,
        )
        self.assertContains(
            response,
            f'name="person_public_ids" value="{person_without_phone.public_id}" data-checkbox-group="dispatch-flow-selection" checked',
            html=False,
        )
