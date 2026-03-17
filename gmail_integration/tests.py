import json
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from common.constants import ACTIVE_ORGANIZATION_SESSION_KEY
from gmail_integration.models import GmailCredential, GmailDispatch, GmailDispatchRecipient, GmailTemplate
from gmail_integration.services import GmailCredentialService
from integrations.models import AppCatalog, OrganizationAppInstallation
from organizations.models import Organization, OrganizationMembership
from people.services import PersonService


class GmailModuleTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='gmail-owner@example.com',
            full_name='Gmail Owner',
            password='StrongPass123!',
        )
        self.user = User.objects.create_user(
            email='gmail-user@example.com',
            full_name='Gmail User',
            password='StrongPass123!',
        )
        self.organization = Organization.objects.create(
            name='Gmail Org',
            slug='gmail-org',
            segment=Organization.Segment.TECHNOLOGY,
            team_size=Organization.TeamSize.SIZE_1_10,
            created_by=self.owner,
        )
        self.other_organization = Organization.objects.create(
            name='Other Gmail Org',
            slug='other-gmail-org',
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

        self.gmail_app = AppCatalog.objects.get(code='gmail')
        self.installation = OrganizationAppInstallation.objects.create(
            organization=self.organization,
            app=self.gmail_app,
            status=OrganizationAppInstallation.Status.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        self.person = PersonService.create_person(
            user=self.owner,
            organization=self.organization,
            first_name='Ana',
            last_name='Costa',
            email='ana@example.com',
            phone='+55 11 99999-0001',
        )
        self.cc_person = PersonService.create_person(
            user=self.owner,
            organization=self.organization,
            first_name='Bruno',
            last_name='Lima',
            email='bruno@example.com',
            phone='+55 11 99999-0002',
        )

    def activate_organization(self, organization):
        session = self.client.session
        session[ACTIVE_ORGANIZATION_SESSION_KEY] = organization.id
        session.save()

    def build_uploaded_json(self, file_name, payload):
        return SimpleUploadedFile(
            file_name,
            json.dumps(payload).encode('utf-8'),
            content_type='application/json',
        )

    def save_gmail_configuration(self):
        return GmailCredentialService.save_configuration(
            user=self.owner,
            organization=self.organization,
            sender_email='sender@gmail.com',
            credentials_file=self.build_uploaded_json(
                'credentials.json',
                {
                    'installed': {
                        'client_id': 'client-id',
                        'client_secret': 'client-secret',
                    }
                },
            ),
            token_file=self.build_uploaded_json(
                'token.json',
                {
                    'token': 'token-value',
                    'refresh_token': 'refresh-token',
                    'token_uri': 'https://oauth2.googleapis.com/token',
                    'client_id': 'client-id',
                    'client_secret': 'client-secret',
                    'scopes': ['https://www.googleapis.com/auth/gmail.send'],
                },
            ),
        )

    def test_save_configuration_persists_encrypted_json(self):
        credential = self.save_gmail_configuration()

        self.assertEqual(credential.sender_email, 'sender@gmail.com')
        stored_credential = GmailCredential.objects.get(pk=credential.pk)
        self.assertTrue(stored_credential.sender_email)

    @patch('gmail_integration.gmail_client.GmailApiGateway.send_email')
    def test_dispatch_create_sends_email_and_persists_message_ids(self, send_email_mock):
        self.save_gmail_configuration()
        send_email_mock.return_value = {
            'message_id': 'gmail-message-1',
            'thread_id': 'gmail-thread-1',
            'refreshed_token_payload': None,
        }

        self.client.force_login(self.owner)
        self.activate_organization(self.organization)
        template = GmailTemplate.objects.create(
            organization=self.organization,
            name='Template Base',
            subject='Ola ${nome}',
            body='Mensagem para ${email}',
            is_active=True,
            created_by=self.owner,
            updated_by=self.owner,
        )

        response = self.client.post(
            reverse('gmail_integration:create_dispatch'),
            {
                'template_public_id': str(template.public_id),
                'person_public_ids': [str(self.person.public_id)],
                'cc_person_public_ids': [str(self.cc_person.public_id)],
                'subject': '',
                'body': '',
            },
        )

        self.assertEqual(response.status_code, 302)
        dispatch = GmailDispatch.objects.get()
        recipient = GmailDispatchRecipient.objects.get(dispatch=dispatch)
        self.assertEqual(dispatch.success_recipients, 1)
        self.assertEqual(recipient.gmail_message_id, 'gmail-message-1')
        self.assertEqual(recipient.gmail_thread_id, 'gmail-thread-1')

    def test_sidebar_shows_gmail_for_installed_app(self):
        self.client.force_login(self.owner)
        self.activate_organization(self.organization)

        response = self.client.get(reverse('dashboard:home'))

        self.assertContains(response, 'Gmail')
        self.assertContains(response, reverse('gmail_integration:dashboard'))
