from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from bot_conversa.models import BotConversaFlowCache
from common.constants import ACTIVE_ORGANIZATION_SESSION_KEY
from gmail_integration.models import GmailTemplate
from hubspot_integration.models import HubSpotPipelineCache
from integrations.models import AppCatalog, OrganizationAppInstallation
from organizations.models import Organization, OrganizationMembership
from people.models import Person
from companies.models import Company
from unittest.mock import patch


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
        self.hubspot_app = AppCatalog.objects.get(code='hubspot')

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

    def test_dispatch_flow_opens_hubspot_preflight_modal_when_hubspot_is_installed(self):
        self.install_app(self.gmail_app)
        self.install_app(self.hubspot_app)
        template = GmailTemplate.objects.create(
            organization=self.organization,
            name='Primeiro contato',
            subject='Ola',
            body='Mensagem',
            is_active=True,
            created_by=self.owner,
            updated_by=self.owner,
        )
        person = Person.objects.create(
            organization=self.organization,
            first_name='Ana',
            last_name='Costa',
            email='ana@example.com',
            phone='+5511999999999',
            created_by=self.owner,
            updated_by=self.owner,
        )

        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.post(
            reverse('dispatch_flow:create_dispatch'),
            {
                'audience_filter': 'all',
                'person_public_ids': [str(person.public_id)],
                'send_gmail': 'on',
                'gmail_template_public_id': str(template.public_id),
                'gmail_min_delay_seconds': '0',
                'gmail_max_delay_seconds': '0',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sincronizar dados com HubSpot?')
        self.assertContains(response, 'hubspot_preflight_modal_submit')

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

    @patch('dispatch_flow.services.GmailDispatchService.create_dispatch')
    @patch('dispatch_flow.services.BotConversaDispatchService.create_dispatch')
    def test_dispatch_flow_redirects_to_unified_detail_when_both_channels_are_created(
        self,
        bot_create_dispatch_mock,
        gmail_create_dispatch_mock,
    ):
        bot_installation = self.install_app(self.bot_conversa_app)
        self.install_app(self.gmail_app)
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
        person = Person.objects.create(
            organization=self.organization,
            first_name='Ana',
            last_name='Costa',
            phone='+5511999999999',
            email='ana@example.com',
            created_by=self.owner,
            updated_by=self.owner,
        )

        bot_dispatch = type('BotDispatchStub', (), {'public_id': '11111111-1111-1111-1111-111111111111'})()
        gmail_dispatch = type('GmailDispatchStub', (), {'public_id': '22222222-2222-2222-2222-222222222222'})()
        bot_create_dispatch_mock.return_value = bot_dispatch
        gmail_create_dispatch_mock.return_value = gmail_dispatch

        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.post(
            reverse('dispatch_flow:create_dispatch'),
            {
                'audience_filter': 'all',
                'person_public_ids': [str(person.public_id)],
                'send_bot_conversa': 'on',
                'send_gmail': 'on',
                'flow_public_id': str(flow.public_id),
                'gmail_template_public_id': str(template.public_id),
                'bot_min_delay_seconds': '0',
                'bot_max_delay_seconds': '0',
                'gmail_min_delay_seconds': '0',
                'gmail_max_delay_seconds': '0',
                'skip_bot_conversa_tag_preflight': '1',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('dispatch_flow:dispatch_detail'), response.url)
        self.assertIn('bot_dispatch=11111111-1111-1111-1111-111111111111', response.url)
        self.assertIn('gmail_dispatch=22222222-2222-2222-2222-222222222222', response.url)

    def test_unified_detail_renders_whatsapp_and_gmail_sections_when_both_ids_are_present(self):
        bot_installation = self.install_app(self.bot_conversa_app)
        self.install_app(self.gmail_app)
        bot_dispatch = bot_installation.organization.bot_conversa_flow_dispatches.create(
            installation=bot_installation,
            flow=BotConversaFlowCache.objects.create(
                organization=self.organization,
                installation=bot_installation,
                external_flow_id='flow-001',
                name='Fluxo principal',
                status=BotConversaFlowCache.Status.ACTIVE,
                last_synced_at=self.organization.created_at,
            ),
            external_flow_id='flow-001',
            flow_name='Fluxo principal',
            status='pending',
            total_items=1,
            min_delay_seconds=0,
            max_delay_seconds=0,
            created_by=self.owner,
            updated_by=self.owner,
        )
        gmail_dispatch = self.organization.gmail_dispatches.create(
            installation=OrganizationAppInstallation.objects.get(organization=self.organization, app=self.gmail_app),
            template=GmailTemplate.objects.create(
                organization=self.organization,
                name='Template',
                subject='Assunto',
                body='Mensagem',
                is_active=True,
                created_by=self.owner,
                updated_by=self.owner,
            ),
            subject_snapshot='Assunto',
            body_snapshot='Mensagem',
            cc_recipients_snapshot=[],
            status='pending',
            total_recipients=1,
            min_delay_seconds=0,
            max_delay_seconds=0,
            created_by=self.owner,
            updated_by=self.owner,
        )

        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.get(
            reverse('dispatch_flow:dispatch_detail'),
            {
                'bot_dispatch': str(bot_dispatch.public_id),
                'gmail_dispatch': str(gmail_dispatch.public_id),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'WhatsApp')
        self.assertContains(response, 'Gmail')
        self.assertContains(response, 'botConversaDispatchPoller')
        self.assertContains(response, 'gmailDispatchPoller')

    def test_unified_detail_renders_only_whatsapp_when_only_bot_dispatch_is_informed(self):
        bot_installation = self.install_app(self.bot_conversa_app)
        bot_dispatch = bot_installation.organization.bot_conversa_flow_dispatches.create(
            installation=bot_installation,
            flow=BotConversaFlowCache.objects.create(
                organization=self.organization,
                installation=bot_installation,
                external_flow_id='flow-001',
                name='Fluxo principal',
                status=BotConversaFlowCache.Status.ACTIVE,
                last_synced_at=self.organization.created_at,
            ),
            external_flow_id='flow-001',
            flow_name='Fluxo principal',
            status='pending',
            total_items=1,
            min_delay_seconds=0,
            max_delay_seconds=0,
            created_by=self.owner,
            updated_by=self.owner,
        )

        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.get(
            reverse('dispatch_flow:dispatch_detail'),
            {
                'bot_dispatch': str(bot_dispatch.public_id),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'WhatsApp')
        self.assertContains(response, 'botConversaDispatchPoller')
        self.assertNotContains(response, 'gmailDispatchPoller')

    def test_unified_detail_renders_only_gmail_when_only_gmail_dispatch_is_informed(self):
        self.install_app(self.gmail_app)
        gmail_dispatch = self.organization.gmail_dispatches.create(
            installation=OrganizationAppInstallation.objects.get(organization=self.organization, app=self.gmail_app),
            template=GmailTemplate.objects.create(
                organization=self.organization,
                name='Template',
                subject='Assunto',
                body='Mensagem',
                is_active=True,
                created_by=self.owner,
                updated_by=self.owner,
            ),
            subject_snapshot='Assunto',
            body_snapshot='Mensagem',
            cc_recipients_snapshot=[],
            status='pending',
            total_recipients=1,
            min_delay_seconds=0,
            max_delay_seconds=0,
            created_by=self.owner,
            updated_by=self.owner,
        )

        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.get(
            reverse('dispatch_flow:dispatch_detail'),
            {
                'gmail_dispatch': str(gmail_dispatch.public_id),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Gmail')
        self.assertContains(response, 'gmailDispatchPoller')
        self.assertNotContains(response, 'botConversaDispatchPoller')

    @patch('dispatch_flow.services.GmailDispatchService.create_dispatch')
    @patch('dispatch_flow.services.HubSpotDealService.create_deal')
    @patch('dispatch_flow.services.HubSpotContactService.sync_people')
    @patch('dispatch_flow.services.HubSpotCompanyService.sync_companies')
    def test_dispatch_flow_applies_hubspot_sync_and_creates_deal_before_dispatch(
        self,
        sync_companies_mock,
        sync_people_mock,
        create_deal_mock,
        gmail_create_dispatch_mock,
    ):
        self.install_app(self.gmail_app)
        hubspot_installation = self.install_app(self.hubspot_app)
        template = GmailTemplate.objects.create(
            organization=self.organization,
            name='Primeiro contato',
            subject='Ola',
            body='Mensagem',
            is_active=True,
            created_by=self.owner,
            updated_by=self.owner,
        )
        company = Company.objects.create(
            organization=self.organization,
            name='ACME',
            website='https://acme.test',
            created_by=self.owner,
            updated_by=self.owner,
        )
        person = Person.objects.create(
            organization=self.organization,
            first_name='Ana',
            last_name='Costa',
            email='ana@acme.test',
            phone='+5511999999999',
            company=company,
            created_by=self.owner,
            updated_by=self.owner,
        )
        pipeline = HubSpotPipelineCache.objects.create(
            organization=self.organization,
            installation=hubspot_installation,
            hubspot_pipeline_id='pipeline-1',
            name='Pipeline Comercial',
            object_type='deals',
            raw_payload={'id': 'pipeline-1', 'stages': [{'id': 'appointmentscheduled', 'label': 'Qualificacao'}]},
            last_synced_at=self.organization.created_at,
        )

        sync_companies_mock.return_value = [company]
        sync_people_mock.return_value = [person]
        create_deal_mock.return_value = type('HubSpotDealStub', (), {'name': 'ACME'})()
        gmail_create_dispatch_mock.return_value = type('GmailDispatchStub', (), {'public_id': '33333333-3333-3333-3333-333333333333'})()

        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.post(
            reverse('dispatch_flow:create_dispatch'),
            {
                'audience_filter': 'all',
                'person_public_ids': [str(person.public_id)],
                'send_gmail': 'on',
                'gmail_template_public_id': str(template.public_id),
                'gmail_min_delay_seconds': '0',
                'gmail_max_delay_seconds': '0',
                'hubspot_preflight_modal_submit': 'apply',
                'hubspot_create_deal_now': 'on',
                'hubspot_deal_target_type': 'company',
                'hubspot_target_company_public_id': str(company.public_id),
                'hubspot_deal_person_public_ids': [str(person.public_id)],
                'hubspot_pipeline_public_id': str(pipeline.public_id),
                'hubspot_stage_id': 'appointmentscheduled',
            },
        )

        self.assertEqual(response.status_code, 302)
        sync_companies_mock.assert_called_once()
        sync_people_mock.assert_called_once()
        create_deal_mock.assert_called_once()
        gmail_create_dispatch_mock.assert_called_once()

    def test_dispatch_flow_rejects_company_deal_contacts_from_other_companies(self):
        self.install_app(self.gmail_app)
        hubspot_installation = self.install_app(self.hubspot_app)
        template = GmailTemplate.objects.create(
            organization=self.organization,
            name='Primeiro contato',
            subject='Ola',
            body='Mensagem',
            is_active=True,
            created_by=self.owner,
            updated_by=self.owner,
        )
        company = Company.objects.create(
            organization=self.organization,
            name='ACME',
            website='https://acme.test',
            hubspot_company_id='company-1',
            created_by=self.owner,
            updated_by=self.owner,
        )
        other_company = Company.objects.create(
            organization=self.organization,
            name='Beta',
            website='https://beta.test',
            hubspot_company_id='company-2',
            created_by=self.owner,
            updated_by=self.owner,
        )
        person = Person.objects.create(
            organization=self.organization,
            first_name='Ana',
            last_name='Costa',
            email='ana@acme.test',
            phone='+5511999999999',
            company=company,
            hubspot_contact_id='contact-1',
            created_by=self.owner,
            updated_by=self.owner,
        )
        wrong_person = Person.objects.create(
            organization=self.organization,
            first_name='Bruno',
            last_name='Souza',
            email='bruno@beta.test',
            phone='+5511988887777',
            company=other_company,
            hubspot_contact_id='contact-2',
            created_by=self.owner,
            updated_by=self.owner,
        )
        pipeline = HubSpotPipelineCache.objects.create(
            organization=self.organization,
            installation=hubspot_installation,
            hubspot_pipeline_id='pipeline-1',
            name='Pipeline Comercial',
            object_type='deals',
            raw_payload={'id': 'pipeline-1', 'stages': [{'id': 'appointmentscheduled', 'label': 'Qualificacao'}]},
            last_synced_at=self.organization.created_at,
        )

        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.post(
            reverse('dispatch_flow:create_dispatch'),
            {
                'audience_filter': 'all',
                'person_public_ids': [str(person.public_id)],
                'send_gmail': 'on',
                'gmail_template_public_id': str(template.public_id),
                'gmail_min_delay_seconds': '0',
                'gmail_max_delay_seconds': '0',
                'hubspot_preflight_modal_submit': 'apply',
                'hubspot_create_deal_now': 'on',
                'hubspot_deal_target_type': 'company',
                'hubspot_target_company_public_id': str(company.public_id),
                'hubspot_deal_person_public_ids': [str(person.public_id), str(wrong_person.public_id)],
                'hubspot_pipeline_public_id': str(pipeline.public_id),
                'hubspot_stage_id': 'appointmentscheduled',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No modo empresa, os contatos do negocio sao definidos automaticamente')

    @patch('dispatch_flow.services.GmailDispatchService.create_dispatch')
    @patch('dispatch_flow.services.HubSpotDealService.create_deal')
    def test_dispatch_flow_creates_company_deals_in_loop_for_selected_companies(
        self,
        create_deal_mock,
        gmail_create_dispatch_mock,
    ):
        self.install_app(self.gmail_app)
        hubspot_installation = self.install_app(self.hubspot_app)
        template = GmailTemplate.objects.create(
            organization=self.organization,
            name='Primeiro contato',
            subject='Ola',
            body='Mensagem',
            is_active=True,
            created_by=self.owner,
            updated_by=self.owner,
        )
        company_a = Company.objects.create(
            organization=self.organization,
            name='ACME',
            hubspot_company_id='company-a',
            created_by=self.owner,
            updated_by=self.owner,
        )
        company_b = Company.objects.create(
            organization=self.organization,
            name='Beta',
            hubspot_company_id='company-b',
            created_by=self.owner,
            updated_by=self.owner,
        )
        person_a = Person.objects.create(
            organization=self.organization,
            first_name='Ana',
            last_name='Costa',
            email='ana@acme.test',
            phone='+5511999999999',
            company=company_a,
            hubspot_contact_id='contact-a',
            created_by=self.owner,
            updated_by=self.owner,
        )
        person_b = Person.objects.create(
            organization=self.organization,
            first_name='Bruno',
            last_name='Souza',
            email='bruno@beta.test',
            phone='+5511988887777',
            company=company_b,
            hubspot_contact_id='contact-b',
            created_by=self.owner,
            updated_by=self.owner,
        )
        pipeline = HubSpotPipelineCache.objects.create(
            organization=self.organization,
            installation=hubspot_installation,
            hubspot_pipeline_id='pipeline-1',
            name='Pipeline Comercial',
            object_type='deals',
            raw_payload={'id': 'pipeline-1', 'stages': [{'id': 'appointmentscheduled', 'label': 'Qualificacao'}]},
            last_synced_at=self.organization.created_at,
        )

        create_deal_mock.side_effect = [
            type('HubSpotDealStub', (), {'name': 'ACME'})(),
            type('HubSpotDealStub', (), {'name': 'Beta'})(),
        ]
        gmail_create_dispatch_mock.return_value = type('GmailDispatchStub', (), {'public_id': '44444444-4444-4444-4444-444444444444'})()

        self.client.force_login(self.owner)
        self.activate_organization()

        response = self.client.post(
            reverse('dispatch_flow:create_dispatch'),
            {
                'audience_filter': 'all',
                'person_public_ids': [str(person_a.public_id), str(person_b.public_id)],
                'send_gmail': 'on',
                'gmail_template_public_id': str(template.public_id),
                'gmail_min_delay_seconds': '0',
                'gmail_max_delay_seconds': '0',
                'hubspot_preflight_modal_submit': 'apply',
                'hubspot_create_deal_now': 'on',
                'hubspot_deal_target_type': 'company',
                'hubspot_pipeline_public_id': str(pipeline.public_id),
                'hubspot_stage_id': 'appointmentscheduled',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(create_deal_mock.call_count, 2)
