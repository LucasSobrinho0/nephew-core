import json
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from common.constants import ACTIVE_ORGANIZATION_SESSION_KEY
from gmail_integration.models import GmailCredential, GmailDispatch, GmailDispatchRecipient, GmailTemplate
from gmail_integration.services import GmailCredentialService, GmailDispatchService
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
                    'email': 'sender@gmail.com',
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
                'min_delay_seconds': 3,
                'max_delay_seconds': 5,
            },
        )

        self.assertEqual(response.status_code, 302)
        dispatch = GmailDispatch.objects.get()
        self.assertEqual(dispatch.status, GmailDispatch.Status.PENDING)
        self.assertEqual(dispatch.min_delay_seconds, 3)
        self.assertEqual(dispatch.max_delay_seconds, 5)

        process_response = self.client.post(
            reverse('gmail_integration:dispatch_process', args=[dispatch.public_id]),
        )

        self.assertEqual(process_response.status_code, 200)
        payload = process_response.json()
        dispatch.refresh_from_db()
        recipient = GmailDispatchRecipient.objects.get(dispatch=dispatch)
        self.assertEqual(dispatch.success_recipients, 1)
        self.assertEqual(dispatch.status, GmailDispatch.Status.COMPLETED)
        self.assertEqual(recipient.gmail_message_id, 'gmail-message-1')
        self.assertEqual(recipient.gmail_thread_id, 'gmail-thread-1')
        self.assertTrue(payload['is_finished'])

    def test_sidebar_shows_gmail_for_installed_app(self):
        self.client.force_login(self.owner)
        self.activate_organization(self.organization)

        response = self.client.get(reverse('dashboard:home'))

        self.assertContains(response, 'Gmail')
        self.assertContains(response, reverse('gmail_integration:dashboard'))

    def test_dispatch_service_rejects_template_from_other_organization(self):
        other_template = GmailTemplate.objects.create(
            organization=self.other_organization,
            name='Outro Template',
            subject='Ola',
            body='Mensagem',
            is_active=True,
            created_by=self.owner,
            updated_by=self.owner,
        )

        self.save_gmail_configuration()

        with self.assertRaisesMessage(ValidationError, 'O template selecionado nao pertence a organizacao ativa.'):
            GmailDispatchService.create_dispatch(
                user=self.owner,
                organization=self.organization,
                template=other_template,
                to_people=[self.person],
                cc_emails=[],
            )

    def test_dispatch_create_form_rejects_max_delay_smaller_than_min(self):
        self.client.force_login(self.owner)
        self.activate_organization(self.organization)

        template = GmailTemplate.objects.create(
            organization=self.organization,
            name='Template Delay',
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
                'min_delay_seconds': 10,
                'max_delay_seconds': 2,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'O delay maximo nao pode ser menor que o delay minimo.')

    def test_dispatch_audience_endpoint_filters_people_already_sent_in_gmail(self):
        dispatch = GmailDispatch.objects.create(
            organization=self.organization,
            installation=self.installation,
            subject_snapshot='Assunto',
            body_snapshot='Corpo',
            status=GmailDispatch.Status.COMPLETED,
            total_recipients=1,
            processed_recipients=1,
            success_recipients=1,
            created_by=self.owner,
            updated_by=self.owner,
        )
        GmailDispatchRecipient.objects.create(
            organization=self.organization,
            dispatch=dispatch,
            person=self.person,
            email_snapshot=self.person.email,
            first_name_snapshot=self.person.first_name,
            last_name_snapshot=self.person.last_name,
            status=GmailDispatchRecipient.Status.SENT,
        )

        self.client.force_login(self.owner)
        self.activate_organization(self.organization)

        response = self.client.get(
            reverse('gmail_integration:dispatch_audience'),
            {'only_unsent': '1'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        labels = [item['label'] for item in payload['items']]
        self.assertTrue(payload['only_unsent'])
        self.assertNotIn(f'{self.person.full_name} - {self.person.email}', labels)
        self.assertIn(f'{self.cc_person.full_name} - {self.cc_person.email}', labels)
