from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from bot_conversa.constants import BOT_CONVERSA_CONTACTS_LIST_PATH
from bot_conversa.client import BotConversaClient
from bot_conversa.models import (
    BotConversaContact,
    BotConversaFlowCache,
    BotConversaFlowDispatch,
    BotConversaFlowDispatchItem,
    BotConversaSyncLog,
)
from bot_conversa.services import BotConversaInstallationService, BotConversaRemoteContactService
from common.constants import ACTIVE_ORGANIZATION_SESSION_KEY
from integrations.models import AppCatalog, OrganizationAppInstallation
from integrations.services import AppCredentialService
from organizations.models import Organization, OrganizationMembership
from people.models import Person
from people.services import PersonService


class FakeBotConversaClient:
    def __init__(self):
        self.sent_payloads = []
        self.created_payloads = []

    def list_contacts(self, search=''):
        return []

    def search_contact_by_phone(self, *, phone):
        return None

    def create_contact(self, *, first_name, last_name, phone):
        self.created_payloads.append(
            {
                'first_name': first_name,
                'last_name': last_name,
                'phone': phone,
            }
        )
        return {
            'external_subscriber_id': 'subscriber-001',
            'name': f'{first_name} {last_name}'.strip(),
            'phone': phone,
            'status': 'active',
            'raw_payload': {'id': 'subscriber-001', 'phone': phone},
        }

    def send_flow(self, *, flow_id, subscriber_id):
        self.sent_payloads.append({'flow_id': flow_id, 'subscriber_id': subscriber_id})
        return {
            'status': 'accepted',
            'message_id': 'message-001',
            'raw_payload': {'id': 'message-001'},
        }


class BotConversaClientUnitTests(TestCase):
    def test_normalize_api_phone_matches_bot_conversa_script_behavior(self):
        self.assertEqual(BotConversaClient._normalize_api_phone('+55 (11) 91234-5678'), '+5511912345678')
        self.assertEqual(BotConversaClient._normalize_api_phone('(11) 91234-5678'), '11912345678')

    @patch.object(BotConversaClient, '_request')
    def test_list_contacts_uses_subscribers_endpoint_and_follows_pagination(self, request_mock):
        request_mock.side_effect = [
            {
                'count': 2,
                'next': 'https://backend.botconversa.com.br/api/v1/webhook/subscribers/?page=2',
                'results': [
                    {'id': 1, 'full_name': 'Ana Costa', 'phone': '5511912345678', 'status': 'active'},
                ],
            },
            {
                'count': 2,
                'next': None,
                'results': [
                    {'id': 2, 'full_name': 'Bruno Lima', 'phone': '5511987654321', 'status': 'active'},
                ],
            },
        ]

        client = BotConversaClient(api_key='fake-key')

        contacts = client.list_contacts()

        self.assertEqual(len(contacts), 2)
        self.assertEqual(request_mock.call_count, 2)
        self.assertEqual(request_mock.call_args_list[0].args[1], BOT_CONVERSA_CONTACTS_LIST_PATH)
        self.assertEqual(request_mock.call_args_list[0].kwargs['query'], {'page': 1})
        self.assertEqual(request_mock.call_args_list[1].kwargs['query'], {'page': 2})


class BotConversaModuleTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='bot-owner@example.com',
            full_name='Bot Owner',
            password='StrongPass123!',
        )
        self.user = User.objects.create_user(
            email='bot-user@example.com',
            full_name='Bot User',
            password='StrongPass123!',
        )

        self.organization = Organization.objects.create(
            name='Alpha Bot Org',
            slug='alpha-bot-org',
            segment=Organization.Segment.TECHNOLOGY,
            team_size=Organization.TeamSize.SIZE_1_10,
            created_by=self.owner,
        )
        self.other_organization = Organization.objects.create(
            name='Beta Bot Org',
            slug='beta-bot-org',
            segment=Organization.Segment.SERVICES,
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
            user=self.owner,
            organization=self.other_organization,
            role=OrganizationMembership.Role.OWNER,
            invited_by=self.owner,
        )
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.organization,
            role=OrganizationMembership.Role.USER,
            invited_by=self.owner,
        )

        self.bot_conversa_app = AppCatalog.objects.get(code='bot_conversa')
        self.installation = OrganizationAppInstallation.objects.create(
            organization=self.organization,
            app=self.bot_conversa_app,
            status=OrganizationAppInstallation.Status.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        AppCredentialService.save_api_key(
            user=self.owner,
            organization=self.organization,
            installation=self.installation,
            api_key='bot-tenant-secret',
        )

        self.person = PersonService.create_person(
            user=self.owner,
            organization=self.organization,
            first_name='Ana',
            last_name='Costa',
            phone='(11) 91234-5678',
        )
        self.flow_cache = BotConversaFlowCache.objects.create(
            organization=self.organization,
            installation=self.installation,
            external_flow_id='8325072',
            name='Welcome Flow',
            status=BotConversaFlowCache.Status.ACTIVE,
            description='Welcome sequence',
            last_synced_at=self.installation.created_at,
            raw_payload={'id': 8325072},
        )

    def activate_organization(self, organization):
        session = self.client.session
        session[ACTIVE_ORGANIZATION_SESSION_KEY] = organization.id
        session.save()

    def test_sidebar_lists_only_installed_apps_for_active_organization(self):
        self.client.force_login(self.owner)
        self.activate_organization(self.organization)

        response = self.client.get(reverse('dashboard:home'))

        self.assertContains(response, 'Bot Conversa')
        self.assertContains(response, reverse('bot_conversa:dashboard'))

        self.activate_organization(self.other_organization)
        response = self.client.get(reverse('dashboard:home'))

        self.assertNotContains(response, reverse('bot_conversa:dashboard'))

    def test_bot_conversa_installation_service_uses_api_key_from_database(self):
        installation, api_key = BotConversaInstallationService.get_api_key(
            organization=self.organization,
        )

        self.assertEqual(installation.pk, self.installation.pk)
        self.assertEqual(api_key, 'bot-tenant-secret')

    def test_dispatches_page_lists_unknown_status_flows_in_selector(self):
        self.flow_cache.status = BotConversaFlowCache.Status.UNKNOWN
        self.flow_cache.save(update_fields=['status', 'updated_at'])
        self.client.force_login(self.owner)
        self.activate_organization(self.organization)

        response = self.client.get(reverse('bot_conversa:dispatches'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.flow_cache.name)
        self.assertContains(response, str(self.flow_cache.public_id))

    @patch('bot_conversa.services.BotConversaInstallationService.build_client')
    def test_sync_person_creates_local_link_with_remote_subscriber(self, build_client_mock):
        fake_client = FakeBotConversaClient()
        build_client_mock.return_value = fake_client
        self.client.force_login(self.owner)
        self.activate_organization(self.organization)

        response = self.client.post(
            reverse('bot_conversa:sync_person'),
            {
                'person_public_id': self.person.public_id,
                'next': reverse('bot_conversa:people'),
            },
        )

        self.assertEqual(response.status_code, 302)
        contact_link = BotConversaContact.objects.get(person=self.person)
        self.person.refresh_from_db()
        self.assertEqual(contact_link.external_subscriber_id, 'subscriber-001')
        self.assertEqual(contact_link.sync_status, BotConversaContact.SyncStatus.SYNCED)
        self.assertEqual(self.person.bot_conversa_id, 'subscriber-001')
        self.assertEqual(fake_client.created_payloads[0]['phone'], self.person.normalized_phone)

    def test_save_remote_contact_creates_person_and_persists_bot_conversa_id(self):
        self.client.force_login(self.owner)
        self.activate_organization(self.organization)

        response = self.client.post(
            reverse('bot_conversa:save_remote_contact'),
            {
                'external_subscriber_id': 'subscriber-remote-001',
                'first_name': 'Marina',
                'last_name': 'Silva',
                'external_name': 'Marina Silva',
                'phone': '+55 11 97777-0000',
                'next': reverse('bot_conversa:contacts'),
            },
        )

        self.assertEqual(response.status_code, 302)
        person = Person.objects.get(organization=self.organization, bot_conversa_id='subscriber-remote-001')
        self.assertEqual(person.first_name, 'Marina')
        self.assertEqual(person.last_name, 'Silva')
        self.assertTrue(
            BotConversaContact.objects.filter(
                organization=self.organization,
                person=person,
                external_subscriber_id='subscriber-remote-001',
            ).exists()
        )

    def test_save_remote_contact_updates_existing_person_with_same_phone(self):
        existing_person = PersonService.create_person(
            user=self.owner,
            organization=self.organization,
            first_name='Carlos',
            last_name='Souza',
            phone='+55 11 98888-0000',
        )

        self.client.force_login(self.owner)
        self.activate_organization(self.organization)

        response = self.client.post(
            reverse('bot_conversa:save_remote_contact'),
            {
                'external_subscriber_id': 'subscriber-remote-002',
                'first_name': 'Carlos',
                'last_name': 'Souza',
                'external_name': 'Carlos Souza',
                'phone': '+55 11 98888-0000',
                'next': reverse('bot_conversa:contacts'),
            },
        )

        self.assertEqual(response.status_code, 302)
        existing_person.refresh_from_db()
        self.assertEqual(existing_person.bot_conversa_id, 'subscriber-remote-002')
        self.assertEqual(Person.objects.filter(organization=self.organization, normalized_phone='5511988880000').count(), 1)

    def test_save_contact_to_crm_raises_validation_error_when_contact_cannot_be_saved(self):
        with self.assertRaises(ValidationError):
            BotConversaRemoteContactService.save_contact_to_crm(
                user=self.owner,
                organization=self.organization,
                external_subscriber_id='',
                phone='',
            )

    def test_save_remote_contact_persists_sync_log_with_contact_link(self):
        self.client.force_login(self.owner)
        self.activate_organization(self.organization)

        response = self.client.post(
            reverse('bot_conversa:save_remote_contact'),
            {
                'external_subscriber_id': 'subscriber-remote-003',
                'first_name': 'Julia',
                'last_name': 'Prado',
                'external_name': 'Julia Prado',
                'phone': '+55 11 97777-0001',
                'next': reverse('bot_conversa:contacts'),
            },
        )

        self.assertEqual(response.status_code, 302)
        sync_log = BotConversaSyncLog.objects.filter(
            organization=self.organization,
            person__bot_conversa_id='subscriber-remote-003',
        ).latest('created_at')
        self.assertIsNotNone(sync_log.contact_link_id)

    def test_user_role_cannot_sync_person(self):
        self.client.force_login(self.user)
        self.activate_organization(self.organization)

        response = self.client.post(
            reverse('bot_conversa:sync_person'),
            {
                'person_public_id': self.person.public_id,
                'next': reverse('bot_conversa:people'),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], reverse('bot_conversa:dashboard'))
        self.assertFalse(BotConversaContact.objects.filter(person=self.person).exists())

    @patch('bot_conversa.services.BotConversaInstallationService.build_client')
    def test_dispatch_process_updates_status_progressively(self, build_client_mock):
        fake_client = FakeBotConversaClient()
        build_client_mock.return_value = fake_client
        self.client.force_login(self.owner)
        self.activate_organization(self.organization)

        create_response = self.client.post(
            reverse('bot_conversa:create_dispatch'),
            {
                'flow_public_id': self.flow_cache.public_id,
                'person_public_ids': [str(self.person.public_id)],
                'min_delay_seconds': 2,
                'max_delay_seconds': 4,
            },
        )

        self.assertEqual(create_response.status_code, 302)
        dispatch = BotConversaFlowDispatch.objects.get(flow=self.flow_cache)

        process_response = self.client.post(
            reverse('bot_conversa:dispatch_process', args=[dispatch.public_id]),
        )

        self.assertEqual(process_response.status_code, 200)
        payload = process_response.json()
        dispatch.refresh_from_db()
        self.assertEqual(dispatch.status, BotConversaFlowDispatch.Status.COMPLETED)
        self.assertEqual(dispatch.min_delay_seconds, 2)
        self.assertEqual(dispatch.max_delay_seconds, 4)
        self.assertEqual(payload['success_items'], 1)
        self.assertTrue(payload['is_finished'])
        self.assertEqual(fake_client.sent_payloads[0]['flow_id'], '8325072')

    def test_dispatch_audience_endpoint_filters_people_already_sent_on_whatsapp(self):
        dispatch = BotConversaFlowDispatch.objects.create(
            organization=self.organization,
            installation=self.installation,
            flow=self.flow_cache,
            external_flow_id=self.flow_cache.external_flow_id,
            flow_name=self.flow_cache.name,
            status=BotConversaFlowDispatch.Status.COMPLETED,
            total_items=1,
            processed_items=1,
            success_items=1,
            created_by=self.owner,
            updated_by=self.owner,
        )
        BotConversaFlowDispatchItem.objects.create(
            organization=self.organization,
            dispatch=dispatch,
            person=self.person,
            target_name=self.person.full_name,
            target_phone=self.person.phone,
            status=BotConversaFlowDispatchItem.Status.SUCCESS,
        )
        other_person = PersonService.create_person(
            user=self.owner,
            organization=self.organization,
            first_name='Bruna',
            last_name='Silva',
            phone='+55 11 96666-0000',
        )

        self.client.force_login(self.owner)
        self.activate_organization(self.organization)

        response = self.client.get(
            reverse('bot_conversa:dispatch_audience'),
            {'only_unsent': '1'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        labels = [item['label'] for item in payload['items']]
        self.assertTrue(payload['only_unsent'])
        self.assertNotIn(f'{self.person.full_name} - {self.person.phone}', labels)
        self.assertIn(f'{other_person.full_name} - {other_person.phone}', labels)
