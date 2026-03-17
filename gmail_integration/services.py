import json
from datetime import datetime

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from gmail_integration.constants import GMAIL_APP_CODE, GMAIL_SEND_SCOPE
from gmail_integration.exceptions import GmailApiError, GmailConfigurationError
from gmail_integration.gmail_client import GmailApiGateway
from gmail_integration.models import GmailDispatch, GmailDispatchRecipient
from gmail_integration.repositories import (
    GmailCredentialRepository,
    GmailDispatchRecipientRepository,
    GmailDispatchRepository,
    GmailTemplateRepository,
)
from integrations.repositories import AppCatalogRepository, AppInstallationRepository
from organizations.repositories import MembershipRepository
from people.repositories import PersonRepository


class GmailAuthorizationService:
    @staticmethod
    def ensure_membership(*, user, organization):
        membership = MembershipRepository.get_for_user_and_organization(user, organization)
        if membership is None:
            raise PermissionDenied('Você não faz parte da organização ativa.')
        return membership

    @staticmethod
    def ensure_operator_access(*, user, organization):
        membership = GmailAuthorizationService.ensure_membership(user=user, organization=organization)
        if not membership.can_manage_integrations:
            raise PermissionDenied('Somente proprietarios e administradores podem operar o Gmail.')
        return membership


class GmailInstallationService:
    @staticmethod
    def get_installation(*, organization):
        app = AppCatalogRepository.get_by_code(GMAIL_APP_CODE)
        if app is None:
            raise GmailConfigurationError('O Gmail nao esta registrado no catalogo de aplicativos.')

        installation = AppInstallationRepository.get_for_organization_and_app(organization, app)
        if installation is None or not installation.is_installed:
            raise ValidationError('Instale o Gmail para a organização ativa antes de usar este módulo.')
        return installation

    @staticmethod
    def get_active_credential(*, organization):
        installation = GmailInstallationService.get_installation(organization=organization)
        credential = GmailCredentialRepository.get_for_installation(installation)
        if credential is None:
            raise GmailConfigurationError('Configure o credentials.json e o token.json antes de enviar emails pelo Gmail.')
        return installation, credential


class GmailCredentialService:
    @staticmethod
    def ensure_installation_access(*, organization, installation):
        if installation.organization_id != organization.id:
            raise PermissionDenied('A instalação selecionada não pertence à organização ativa.')
        if installation.app.code != GMAIL_APP_CODE:
            raise ValidationError('A instalacao selecionada nao pertence ao aplicativo Gmail.')
        if not installation.is_installed:
            raise ValidationError('Instale o Gmail antes de configurar as credenciais.')

    @staticmethod
    @transaction.atomic
    def save_configuration(*, user, organization, credentials_file, token_file):
        GmailAuthorizationService.ensure_operator_access(user=user, organization=organization)
        installation = GmailInstallationService.get_installation(organization=organization)
        GmailCredentialService.ensure_installation_access(organization=organization, installation=installation)

        credentials_payload = GmailCredentialService.parse_uploaded_json(credentials_file, 'credentials.json')
        token_payload = GmailCredentialService.parse_uploaded_json(token_file, 'token.json')

        GmailCredentialService.validate_credentials_payload(credentials_payload)
        GmailCredentialService.validate_token_payload(token_payload)

        sender_email = GmailCredentialService.extract_sender_email(token_payload)
        scopes = token_payload.get('scopes') or [GMAIL_SEND_SCOPE]
        token_expires_at = GmailCredentialService.parse_token_expiry(token_payload)
        serialized_credentials = json.dumps(credentials_payload, ensure_ascii=False, sort_keys=True)
        serialized_token = json.dumps(token_payload, ensure_ascii=False, sort_keys=True)

        existing_credential = GmailCredentialRepository.get_for_installation(installation)
        if existing_credential is None:
            return GmailCredentialRepository.create(
                organization=organization,
                installation=installation,
                sender_email=sender_email,
                credentials_json=serialized_credentials,
                token_json=serialized_token,
                scopes=scopes,
                token_expires_at=token_expires_at,
                created_by=user,
                updated_by=user,
            )

        existing_credential.sender_email = sender_email
        existing_credential.credentials_json = serialized_credentials
        existing_credential.token_json = serialized_token
        existing_credential.scopes = scopes
        existing_credential.token_expires_at = token_expires_at
        existing_credential.updated_by = user
        existing_credential.save(
            update_fields=[
                'sender_email',
                'credentials_json',
                'token_json',
                'scopes',
                'token_expires_at',
                'updated_by',
                'updated_at',
            ]
        )
        return existing_credential

    @staticmethod
    def parse_uploaded_json(uploaded_file, expected_name):
        if uploaded_file is None:
            raise ValidationError(f'Envie o arquivo {expected_name}.')

        try:
            raw_content = uploaded_file.read().decode('utf-8')
        except UnicodeDecodeError as exc:
            raise ValidationError(f'O arquivo {expected_name} deve estar em UTF-8.') from exc

        try:
            payload = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise ValidationError(f'O arquivo {expected_name} precisa conter um JSON valido.') from exc

        if not isinstance(payload, dict):
            raise ValidationError(f'O arquivo {expected_name} precisa conter um objeto JSON.')

        return payload

    @staticmethod
    def validate_credentials_payload(credentials_payload):
        if not credentials_payload.get('installed') and not credentials_payload.get('web'):
            raise ValidationError('O credentials.json precisa conter a configuracao "installed" ou "web".')

    @staticmethod
    def extract_sender_email(token_payload):
        possible_keys = (
            'email',
            'user_email',
            'account',
            'account_email',
        )
        for key_name in possible_keys:
            resolved_value = (token_payload.get(key_name) or '').strip().lower()
            if resolved_value:
                return resolved_value
        return ''

    @staticmethod
    def validate_token_payload(token_payload):
        required_keys = {'client_id', 'client_secret', 'refresh_token', 'token_uri'}
        missing_keys = sorted(required_keys.difference(token_payload.keys()))
        if missing_keys:
            missing_keys_label = ', '.join(missing_keys)
            raise ValidationError(f'O token.json nao possui os campos obrigatorios: {missing_keys_label}.')

    @staticmethod
    def parse_token_expiry(token_payload):
        expiry_value = token_payload.get('expiry')
        if not expiry_value:
            return None

        normalized_value = expiry_value.replace('Z', '+00:00')
        try:
            parsed_expiry = datetime.fromisoformat(normalized_value)
        except ValueError:
            return None

        if timezone.is_naive(parsed_expiry):
            return timezone.make_aware(parsed_expiry, timezone.utc)
        return parsed_expiry

    @staticmethod
    def persist_refreshed_token(*, credential, refreshed_token_payload):
        if not refreshed_token_payload:
            return credential

        credential.token_json = json.dumps(refreshed_token_payload, ensure_ascii=False, sort_keys=True)
        credential.scopes = refreshed_token_payload.get('scopes') or credential.scopes
        credential.token_expires_at = GmailCredentialService.parse_token_expiry(refreshed_token_payload)
        credential.save(update_fields=['token_json', 'scopes', 'token_expires_at', 'updated_at'])
        return credential


class GmailTemplateRenderService:
    @staticmethod
    def render(content, person):
        rendered_content = content
        replacement_map = {
            '${nome}': person.first_name,
            '${sobrenome}': person.last_name,
            '${email}': person.email or '',
        }

        for placeholder, resolved_value in replacement_map.items():
            rendered_content = rendered_content.replace(placeholder, resolved_value or '')

        return rendered_content


class GmailTemplateService:
    @staticmethod
    @transaction.atomic
    def create_template(*, user, organization, name, subject, body, is_active):
        GmailAuthorizationService.ensure_operator_access(user=user, organization=organization)

        try:
            return GmailTemplateRepository.create(
                organization=organization,
                name=name,
                subject=subject,
                body=body,
                is_active=is_active,
                created_by=user,
                updated_by=user,
            )
        except IntegrityError as exc:
            raise ValidationError('Já existe um template com este nome na organização ativa.') from exc

    @staticmethod
    @transaction.atomic
    def update_template(*, user, organization, template, name, subject, body, is_active):
        GmailAuthorizationService.ensure_operator_access(user=user, organization=organization)

        if template.organization_id != organization.id:
            raise ValidationError('O template selecionado não pertence à organização ativa.')

        template.name = name
        template.subject = subject
        template.body = body
        template.is_active = is_active
        template.updated_by = user

        try:
            template.save(update_fields=['name', 'subject', 'body', 'is_active', 'updated_by', 'updated_at'])
        except IntegrityError as exc:
            raise ValidationError('Já existe um template com este nome na organização ativa.') from exc

        return template


class GmailDispatchService:
    @staticmethod
    @transaction.atomic
    def create_dispatch(*, user, organization, template, to_people, cc_emails):
        GmailAuthorizationService.ensure_operator_access(user=user, organization=organization)
        installation, credential = GmailInstallationService.get_active_credential(organization=organization)

        resolved_subject, resolved_body = GmailDispatchService.resolve_message_content(template=template)
        cc_recipients_snapshot = GmailDispatchService.build_cc_snapshot(cc_emails)
        GmailDispatchService.validate_people_for_dispatch(
            organization=organization,
            to_people=to_people,
        )

        dispatch = GmailDispatchRepository.create(
            organization=organization,
            installation=installation,
            template=template,
            subject_snapshot=resolved_subject,
            body_snapshot=resolved_body,
            cc_recipients_snapshot=cc_recipients_snapshot,
            status=GmailDispatch.Status.PENDING,
            total_recipients=len(to_people),
            created_by=user,
            updated_by=user,
        )

        for person in to_people:
            GmailDispatchRecipientRepository.create(
                organization=organization,
                dispatch=dispatch,
                person=person,
                email_snapshot=person.email,
                first_name_snapshot=person.first_name,
                last_name_snapshot=person.last_name,
                status=GmailDispatchRecipient.Status.PENDING,
            )

        GmailDispatchService.process_dispatch(
            organization=organization,
            dispatch=dispatch,
            credential=credential,
        )
        return dispatch

    @staticmethod
    def resolve_message_content(*, template):
        if template is None:
            raise ValidationError('Selecione um template salvo para o disparo.')
        return template.subject, template.body

    @staticmethod
    def build_cc_snapshot(cc_emails):
        cc_snapshot = []
        for email_address in cc_emails:
            cc_snapshot.append(
                {
                    'email': email_address,
                }
            )
        return cc_snapshot

    @staticmethod
    def validate_people_for_dispatch(*, organization, to_people):
        if not to_people:
            raise ValidationError('Selecione pelo menos um destinatario para o disparo.')

        for person in to_people:
            if person.organization_id != organization.id:
                raise ValidationError('Existe uma pessoa que não pertence à organização ativa.')
            if not person.email:
                raise ValidationError(f'{person.full_name} nao possui email cadastrado.')

    @staticmethod
    @transaction.atomic
    def process_dispatch(*, organization, dispatch, credential=None):
        if dispatch.organization_id != organization.id:
            raise ValidationError('O disparo selecionado não pertence à organização ativa.')

        if credential is None:
            _installation, credential = GmailInstallationService.get_active_credential(organization=organization)

        token_payload = json.loads(credential.token_json)
        gateway = GmailApiGateway(
            token_payload=token_payload,
            required_scopes=credential.scopes or [GMAIL_SEND_SCOPE],
        )
        cc_emails = [cc_recipient['email'] for cc_recipient in dispatch.cc_recipients_snapshot]
        dispatch_recipients = list(GmailDispatchRecipientRepository.list_for_dispatch(dispatch))

        dispatch.status = GmailDispatch.Status.RUNNING
        dispatch.started_at = dispatch.started_at or timezone.now()
        dispatch.error_summary = ''
        dispatch.save(update_fields=['status', 'started_at', 'error_summary', 'updated_at'])

        refreshed_token_payload = None
        for dispatch_recipient in dispatch_recipients:
            try:
                rendered_subject = GmailTemplateRenderService.render(dispatch.subject_snapshot, dispatch_recipient.person)
                rendered_body = GmailTemplateRenderService.render(dispatch.body_snapshot, dispatch_recipient.person)
                send_result = gateway.send_email(
                    recipient_email=dispatch_recipient.email_snapshot,
                    subject=rendered_subject,
                    body=rendered_body,
                    cc_emails=cc_emails,
                )
                refreshed_token_payload = send_result.get('refreshed_token_payload') or refreshed_token_payload
                dispatch_recipient.status = GmailDispatchRecipient.Status.SENT
                dispatch_recipient.gmail_message_id = send_result.get('message_id', '')
                dispatch_recipient.gmail_thread_id = send_result.get('thread_id', '')
                dispatch_recipient.error_message = ''
                dispatch_recipient.sent_at = timezone.now()
                dispatch_recipient.save(
                    update_fields=[
                        'status',
                        'gmail_message_id',
                        'gmail_thread_id',
                        'error_message',
                        'sent_at',
                        'updated_at',
                    ]
                )
            except (GmailApiError, GmailConfigurationError) as exc:
                dispatch_recipient.status = GmailDispatchRecipient.Status.FAILED
                dispatch_recipient.error_message = str(exc)[:255]
                dispatch_recipient.save(update_fields=['status', 'error_message', 'updated_at'])

        GmailCredentialService.persist_refreshed_token(
            credential=credential,
            refreshed_token_payload=refreshed_token_payload,
        )
        GmailDispatchService.update_dispatch_counters(dispatch=dispatch)
        return dispatch

    @staticmethod
    def update_dispatch_counters(*, dispatch):
        recipients = list(GmailDispatchRecipientRepository.list_for_dispatch(dispatch))
        processed_recipients = sum(1 for recipient in recipients if recipient.status != GmailDispatchRecipient.Status.PENDING)
        success_recipients = sum(1 for recipient in recipients if recipient.status == GmailDispatchRecipient.Status.SENT)
        failed_recipients = sum(1 for recipient in recipients if recipient.status == GmailDispatchRecipient.Status.FAILED)

        dispatch.processed_recipients = processed_recipients
        dispatch.success_recipients = success_recipients
        dispatch.failed_recipients = failed_recipients
        dispatch.finished_at = timezone.now()

        if failed_recipients and success_recipients:
            dispatch.status = GmailDispatch.Status.COMPLETED_WITH_ERRORS
            dispatch.error_summary = 'Parte dos emails falhou durante o disparo.'
        elif failed_recipients:
            dispatch.status = GmailDispatch.Status.FAILED
            dispatch.error_summary = 'Nenhum email foi enviado com sucesso.'
        else:
            dispatch.status = GmailDispatch.Status.COMPLETED
            dispatch.error_summary = ''

        dispatch.save(
            update_fields=[
                'processed_recipients',
                'success_recipients',
                'failed_recipients',
                'finished_at',
                'status',
                'error_summary',
                'updated_at',
            ]
        )
        return dispatch


class GmailDashboardService:
    @staticmethod
    def build_summary(*, organization):
        installation, credential = GmailInstallationService.get_active_credential(organization=organization)
        return {
            'installation': installation,
            'credential': credential,
            'template_count': GmailTemplateRepository.list_for_organization(organization).count(),
            'dispatch_count': GmailDispatchRepository.list_for_organization(organization).count(),
            'recent_dispatches': GmailDispatchRepository.list_recent_for_organization(organization, limit=5),
        }
