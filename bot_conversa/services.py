from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from bot_conversa.client import BotConversaClient
from bot_conversa.constants import BOT_CONVERSA_APP_CODE, DEFAULT_DISPATCH_BATCH_SIZE
from bot_conversa.exceptions import BotConversaApiError, BotConversaConfigurationError
from bot_conversa.models import (
    BotConversaContact,
    BotConversaFlowCache,
    BotConversaFlowDispatch,
    BotConversaFlowDispatchItem,
    BotConversaSyncLog,
)
from bot_conversa.repositories import (
    BotConversaContactRepository,
    BotConversaFlowCacheRepository,
    BotConversaFlowDispatchItemRepository,
    BotConversaFlowDispatchRepository,
    BotConversaSyncLogRepository,
)
from common.phone import normalize_phone
from integrations.repositories import AppCatalogRepository, AppCredentialRepository, AppInstallationRepository
from organizations.repositories import MembershipRepository
from people.repositories import PersonRepository
from people.services import PersonService


class BotConversaAuthorizationService:
    @staticmethod
    def ensure_membership(*, user, organization):
        membership = MembershipRepository.get_for_user_and_organization(user, organization)
        if membership is None:
            raise PermissionDenied('Você não faz parte da organização ativa.')
        return membership

    @staticmethod
    def ensure_operator_access(*, user, organization):
        membership = BotConversaAuthorizationService.ensure_membership(
            user=user,
            organization=organization,
        )
        if not membership.can_manage_integrations:
            raise PermissionDenied('Somente proprietarios e administradores podem operar acoes do Bot Conversa.')
        return membership


class BotConversaInstallationService:
    @staticmethod
    def get_installation(*, organization):
        app = AppCatalogRepository.get_by_code(BOT_CONVERSA_APP_CODE)
        if app is None:
            raise BotConversaConfigurationError('O Bot Conversa nao esta registrado no catalogo de aplicativos.')

        installation = AppInstallationRepository.get_for_organization_and_app(organization, app)
        if installation is None or not installation.is_installed:
            raise ValidationError('Instale o Bot Conversa para a organização ativa antes de usar este módulo.')
        return installation

    @staticmethod
    def get_api_key(*, organization):
        installation = BotConversaInstallationService.get_installation(organization=organization)
        credential = AppCredentialRepository.get_current_api_key(installation)
        if credential is None:
            raise BotConversaConfigurationError('Configure a chave de API do Bot Conversa antes de usar este modulo.')
        return installation, credential.secret_value

    @staticmethod
    def build_client(*, organization):
        _, api_key = BotConversaInstallationService.get_api_key(organization=organization)
        return BotConversaClient(api_key=api_key)


class BotConversaDashboardService:
    @staticmethod
    def build_summary(*, organization):
        installation = BotConversaInstallationService.get_installation(organization=organization)
        recent_dispatches = BotConversaFlowDispatchRepository.list_recent_for_organization(organization, limit=5)
        recent_sync_logs = BotConversaSyncLogRepository.list_recent_for_organization(organization, limit=5)

        return {
            'installation': installation,
            'person_count': PersonRepository.count_for_organization(organization),
            'synced_contact_count': BotConversaContactRepository.list_for_organization(organization).count(),
            'flow_count': BotConversaFlowCacheRepository.list_selectable_for_organization(organization).count(),
            'recent_dispatches': recent_dispatches,
            'recent_sync_logs': recent_sync_logs,
        }


class BotConversaPeopleService:
    @staticmethod
    def create_person(*, user, organization, first_name, last_name, phone, email=''):
        BotConversaAuthorizationService.ensure_operator_access(user=user, organization=organization)
        return PersonService.create_person(
            user=user,
            organization=organization,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
        )

    @staticmethod
    def build_person_rows(*, organization):
        persons = list(PersonRepository.list_for_organization(organization))
        synced_contacts = list(BotConversaContactRepository.list_for_organization(organization))
        contact_by_person_id = {contact.person_id: contact for contact in synced_contacts}

        person_rows = []
        for person in persons:
            contact_link = contact_by_person_id.get(person.id)
            person_rows.append(
                {
                    'person': person,
                    'contact_link': contact_link,
                    'is_synced': bool(contact_link and contact_link.sync_status == BotConversaContact.SyncStatus.SYNCED),
                }
            )

        return person_rows


class BotConversaFlowService:
    @staticmethod
    @transaction.atomic
    def refresh_flows(*, user, organization):
        installation = BotConversaInstallationService.get_installation(organization=organization)
        BotConversaAuthorizationService.ensure_operator_access(user=user, organization=organization)
        client = BotConversaInstallationService.build_client(organization=organization)

        synced_at = timezone.now()
        refreshed_flows = []

        for remote_flow in client.list_flows():
            flow_cache = BotConversaFlowCacheRepository.get_for_organization_and_external_id(
                organization,
                remote_flow['external_flow_id'],
            )
            if flow_cache is None:
                flow_cache = BotConversaFlowCacheRepository.create(
                    organization=organization,
                    installation=installation,
                    external_flow_id=remote_flow['external_flow_id'],
                    name=remote_flow['name'],
                    status=BotConversaFlowService.normalize_flow_status(remote_flow['status']),
                    description=remote_flow['description'],
                    last_synced_at=synced_at,
                    raw_payload=remote_flow['raw_payload'],
                )
            else:
                flow_cache.name = remote_flow['name']
                flow_cache.status = BotConversaFlowService.normalize_flow_status(remote_flow['status'])
                flow_cache.description = remote_flow['description']
                flow_cache.last_synced_at = synced_at
                flow_cache.raw_payload = remote_flow['raw_payload']
                flow_cache.save(update_fields=['name', 'status', 'description', 'last_synced_at', 'raw_payload', 'updated_at'])

            refreshed_flows.append(flow_cache)

        return refreshed_flows

    @staticmethod
    def normalize_flow_status(status):
        allowed_statuses = {choice for choice, _label in BotConversaFlowCache.Status.choices}
        return status if status in allowed_statuses else BotConversaFlowCache.Status.UNKNOWN


class BotConversaContactSyncService:
    @staticmethod
    @transaction.atomic
    def sync_person(*, user, organization, person):
        installation = BotConversaInstallationService.get_installation(organization=organization)
        BotConversaAuthorizationService.ensure_operator_access(user=user, organization=organization)
        BotConversaContactSyncService.ensure_person_access(organization=organization, person=person)

        client = BotConversaInstallationService.build_client(organization=organization)
        remote_phone = person.normalized_phone
        remote_contact = client.search_contact_by_phone(phone=remote_phone)

        if remote_contact is None:
            BotConversaSyncLogRepository.create(
                organization=organization,
                installation=installation,
                person=person,
                actor=user,
                action=BotConversaSyncLog.Action.LOOKUP,
                outcome=BotConversaSyncLog.Outcome.NOT_FOUND,
                message='Contato nao encontrado remotamente. Criando um novo subscriber.',
            )
            remote_contact = client.create_contact(
                first_name=person.first_name,
                last_name=person.last_name,
                phone=remote_phone,
            )
            action = BotConversaSyncLog.Action.CREATE
        else:
            action = BotConversaSyncLog.Action.LINK

        contact_link = BotConversaContactSyncService.upsert_contact_link(
            user=user,
            organization=organization,
            installation=installation,
            person=person,
            remote_contact=remote_contact,
        )

        BotConversaSyncLogRepository.create(
            organization=organization,
            installation=installation,
            person=person,
            contact_link=contact_link,
            actor=user,
            action=action,
            outcome=BotConversaSyncLog.Outcome.SUCCESS,
            message='Contato vinculado com sucesso.',
            remote_payload=remote_contact['raw_payload'],
        )

        return contact_link

    @staticmethod
    def ensure_person_access(*, organization, person):
        if person.organization_id != organization.id:
            raise PermissionDenied('A pessoa selecionada não pertence à organização ativa.')

    @staticmethod
    def upsert_contact_link(*, user, organization, installation, person, remote_contact):
        person = PersonService.assign_bot_conversa_id(
            user=user,
            organization=organization,
            person=person,
            bot_conversa_id=remote_contact['external_subscriber_id'],
        )
        contact_link = BotConversaContactRepository.get_for_organization_and_person(organization, person)

        if contact_link is None:
            try:
                return BotConversaContactRepository.create(
                    organization=organization,
                    installation=installation,
                    person=person,
                    external_subscriber_id=remote_contact['external_subscriber_id'],
                    external_name=remote_contact['name'] or person.full_name,
                    phone=remote_contact['phone'] or person.phone,
                    sync_status=BotConversaContact.SyncStatus.SYNCED,
                    last_synced_at=timezone.now(),
                    remote_payload=remote_contact['raw_payload'],
                    created_by=user,
                    updated_by=user,
                )
            except IntegrityError as exc:
                raise ValidationError('Já existe um contato do Bot Conversa com este subscriber nesta organização.') from exc

        contact_link.external_subscriber_id = remote_contact['external_subscriber_id']
        contact_link.external_name = remote_contact['name'] or person.full_name
        contact_link.phone = remote_contact['phone'] or person.phone
        contact_link.sync_status = BotConversaContact.SyncStatus.SYNCED
        contact_link.last_synced_at = timezone.now()
        contact_link.last_error_message = ''
        contact_link.remote_payload = remote_contact['raw_payload']
        contact_link.updated_by = user
        contact_link.save(
            update_fields=[
                'external_subscriber_id',
                'external_name',
                'phone',
                'normalized_phone',
                'sync_status',
                'last_synced_at',
                'last_error_message',
                'remote_payload',
                'updated_by',
                'updated_at',
            ]
        )
        return contact_link

    @staticmethod
    def ensure_remote_contact(*, user, organization, person):
        return BotConversaContactSyncService.sync_person(
            user=user,
            organization=organization,
            person=person,
        )


class BotConversaRemoteContactService:
    @staticmethod
    def list_contacts(*, organization, search=''):
        installation = BotConversaInstallationService.get_installation(organization=organization)
        client = BotConversaInstallationService.build_client(organization=organization)
        persons = list(PersonRepository.list_for_organization(organization))
        local_contacts = list(BotConversaContactRepository.list_for_organization(organization))
        persons_by_bot_conversa_id = {
            person.bot_conversa_id: person
            for person in persons
            if person.bot_conversa_id
        }
        local_by_subscriber_id = {
            contact.external_subscriber_id: contact
            for contact in local_contacts
        }

        remote_contacts = []
        for remote_contact in client.list_contacts(search=search):
            linked_contact = local_by_subscriber_id.get(remote_contact['external_subscriber_id'])
            linked_person = persons_by_bot_conversa_id.get(remote_contact['external_subscriber_id'])
            if linked_person is None and linked_contact is not None:
                linked_person = linked_contact.person

            remote_contacts.append(
                {
                    'installation': installation,
                    'external_subscriber_id': remote_contact['external_subscriber_id'],
                    'name': remote_contact['name'],
                    'first_name': remote_contact['first_name'],
                    'last_name': remote_contact['last_name'],
                    'phone': remote_contact['phone'],
                    'status': remote_contact['status'],
                    'linked_person': linked_person,
                    'linked_contact': linked_contact,
                    'is_saved_in_crm': linked_person is not None,
                }
            )

        return remote_contacts

    @staticmethod
    @transaction.atomic
    def save_contact_to_crm(*, user, organization, external_subscriber_id, phone, first_name='', last_name='', external_name=''):
        installation = BotConversaInstallationService.get_installation(organization=organization)
        BotConversaAuthorizationService.ensure_operator_access(user=user, organization=organization)

        normalized_bot_conversa_id = (external_subscriber_id or '').strip()
        if not normalized_bot_conversa_id:
            raise ValidationError('O contato remoto nao retornou um ID valido do Bot Conversa.')

        normalized_phone = normalize_phone(phone)
        resolved_first_name, resolved_last_name = BotConversaRemoteContactService.resolve_contact_name(
            first_name=first_name,
            last_name=last_name,
            external_name=external_name,
        )

        person = PersonRepository.get_for_organization_and_bot_conversa_id(
            organization,
            normalized_bot_conversa_id,
        )
        created_person = False
        linked_existing_person = False

        if person is None:
            person = PersonRepository.get_for_organization_and_normalized_phone(
                organization,
                normalized_phone,
            )
            if person is not None:
                person = PersonService.assign_bot_conversa_id(
                    user=user,
                    organization=organization,
                    person=person,
                    bot_conversa_id=normalized_bot_conversa_id,
                )
                linked_existing_person = True
            else:
                person = PersonService.create_person(
                    user=user,
                    organization=organization,
                    first_name=resolved_first_name,
                    last_name=resolved_last_name,
                    phone=phone,
                    bot_conversa_id=normalized_bot_conversa_id,
                )
                created_person = True

        remote_contact = {
            'external_subscriber_id': normalized_bot_conversa_id,
            'name': external_name or person.full_name,
            'phone': phone,
            'status': 'active',
            'raw_payload': {},
        }
        contact_link = BotConversaContactSyncService.upsert_contact_link(
            user=user,
            organization=organization,
            installation=installation,
            person=person,
            remote_contact=remote_contact,
        )

        BotConversaSyncLogRepository.create(
            organization=organization,
            installation=installation,
            person=person,
            contact_link=contact_link,
            actor=user,
            action=BotConversaSyncLog.Action.CREATE if created_person else BotConversaSyncLog.Action.LINK,
            outcome=BotConversaSyncLog.Outcome.SUCCESS,
            message='Contato remoto salvo no CRM.',
            remote_payload=remote_contact['raw_payload'],
        )

        return {
            'person': person,
            'contact_link': contact_link,
            'created_person': created_person,
            'linked_existing_person': linked_existing_person,
        }

    @staticmethod
    def resolve_contact_name(*, first_name='', last_name='', external_name=''):
        cleaned_first_name = (first_name or '').strip()
        cleaned_last_name = (last_name or '').strip()

        if not cleaned_first_name and not cleaned_last_name:
            full_name = (external_name or '').strip()
            if full_name:
                name_parts = full_name.split()
                cleaned_first_name = name_parts[0]
                cleaned_last_name = ' '.join(name_parts[1:])

        cleaned_first_name = cleaned_first_name or 'Contato'
        cleaned_last_name = cleaned_last_name or 'SemSobrenome'
        return cleaned_first_name, cleaned_last_name


class BotConversaDispatchService:
    @staticmethod
    @transaction.atomic
    def create_dispatch(*, user, organization, flow_cache, persons):
        installation = BotConversaInstallationService.get_installation(organization=organization)
        BotConversaAuthorizationService.ensure_operator_access(user=user, organization=organization)
        BotConversaDispatchService.ensure_flow_access(organization=organization, flow_cache=flow_cache)

        unique_persons = []
        seen_person_ids = set()
        for person in persons:
            if person.organization_id != organization.id:
                raise PermissionDenied('Uma ou mais pessoas selecionadas não pertencem à organização ativa.')
            if person.id not in seen_person_ids:
                unique_persons.append(person)
                seen_person_ids.add(person.id)

        if not unique_persons:
            raise ValidationError('Selecione pelo menos uma pessoa para o disparo.')

        dispatch = BotConversaFlowDispatchRepository.create(
            organization=organization,
            installation=installation,
            flow=flow_cache,
            external_flow_id=flow_cache.external_flow_id,
            flow_name=flow_cache.name,
            status=BotConversaFlowDispatch.Status.PENDING,
            total_items=len(unique_persons),
            created_by=user,
            updated_by=user,
        )

        for person in unique_persons:
            BotConversaFlowDispatchItemRepository.create(
                organization=organization,
                dispatch=dispatch,
                person=person,
                target_name=person.full_name,
                target_phone=person.phone,
            )

        return dispatch

    @staticmethod
    def ensure_flow_access(*, organization, flow_cache):
        if flow_cache.organization_id != organization.id:
            raise PermissionDenied('O fluxo selecionado não pertence à organização ativa.')

    @staticmethod
    @transaction.atomic
    def process_pending_items(*, user, organization, dispatch, batch_size=DEFAULT_DISPATCH_BATCH_SIZE):
        BotConversaAuthorizationService.ensure_operator_access(user=user, organization=organization)
        if dispatch.organization_id != organization.id:
            raise PermissionDenied('O disparo selecionado não pertence à organização ativa.')

        if dispatch.status in {
            BotConversaFlowDispatch.Status.COMPLETED,
            BotConversaFlowDispatch.Status.COMPLETED_WITH_ERRORS,
            BotConversaFlowDispatch.Status.FAILED,
        }:
            return dispatch

        client = BotConversaInstallationService.build_client(organization=organization)

        if dispatch.status == BotConversaFlowDispatch.Status.PENDING:
            dispatch.status = BotConversaFlowDispatch.Status.RUNNING
            dispatch.started_at = dispatch.started_at or timezone.now()
            dispatch.updated_by = user
            dispatch.save(update_fields=['status', 'started_at', 'updated_by', 'updated_at'])

        pending_items = list(
            BotConversaFlowDispatchItemRepository.list_pending_for_dispatch(
                dispatch,
                limit=batch_size,
            )
        )

        if not pending_items:
            BotConversaDispatchService.finalize_dispatch(dispatch=dispatch, user=user)
            return dispatch

        for item in pending_items:
            item.status = BotConversaFlowDispatchItem.Status.RUNNING
            item.last_attempt_at = timezone.now()
            item.attempt_count += 1
            item.save(update_fields=['status', 'last_attempt_at', 'attempt_count', 'updated_at'])

            try:
                if item.person is None:
                    raise ValidationError('O item do disparo nao possui uma pessoa interna vinculada.')

                contact_link = BotConversaContactSyncService.ensure_remote_contact(
                    user=user,
                    organization=organization,
                    person=item.person,
                )
                response_payload = client.send_flow(
                    flow_id=dispatch.external_flow_id,
                    subscriber_id=contact_link.external_subscriber_id,
                )
                item.contact_link = contact_link
                item.external_subscriber_id = contact_link.external_subscriber_id
                item.status = BotConversaFlowDispatchItem.Status.SUCCESS
                item.sent_at = timezone.now()
                item.error_message = ''
                item.response_payload = response_payload['raw_payload']
                item.save(
                    update_fields=[
                        'contact_link',
                        'external_subscriber_id',
                        'status',
                        'sent_at',
                        'error_message',
                        'response_payload',
                        'updated_at',
                    ]
                )
            except (BotConversaApiError, BotConversaConfigurationError, PermissionDenied, ValidationError) as exc:
                item.status = BotConversaFlowDispatchItem.Status.FAILED
                item.error_message = str(exc)[:255]
                item.response_payload = {}
                item.save(update_fields=['status', 'error_message', 'response_payload', 'updated_at'])

        BotConversaDispatchService.refresh_dispatch_counters(dispatch=dispatch, user=user)
        return dispatch

    @staticmethod
    def refresh_dispatch_counters(*, dispatch, user):
        items = BotConversaFlowDispatchItemRepository.list_for_dispatch(dispatch)
        processed_items = items.exclude(status=BotConversaFlowDispatchItem.Status.PENDING).count()
        success_items = items.filter(status=BotConversaFlowDispatchItem.Status.SUCCESS).count()
        failed_items = items.filter(status=BotConversaFlowDispatchItem.Status.FAILED).count()

        dispatch.processed_items = processed_items
        dispatch.success_items = success_items
        dispatch.failed_items = failed_items
        dispatch.updated_by = user
        dispatch.save(
            update_fields=[
                'processed_items',
                'success_items',
                'failed_items',
                'updated_by',
                'updated_at',
            ]
        )

        if processed_items >= dispatch.total_items:
            BotConversaDispatchService.finalize_dispatch(dispatch=dispatch, user=user)

    @staticmethod
    def finalize_dispatch(*, dispatch, user):
        if dispatch.failed_items and dispatch.success_items:
            dispatch.status = BotConversaFlowDispatch.Status.COMPLETED_WITH_ERRORS
        elif dispatch.failed_items and not dispatch.success_items:
            dispatch.status = BotConversaFlowDispatch.Status.FAILED
        else:
            dispatch.status = BotConversaFlowDispatch.Status.COMPLETED

        dispatch.finished_at = timezone.now()
        dispatch.updated_by = user
        dispatch.error_summary = 'Alguns contatos nao puderam receber o fluxo.' if dispatch.failed_items else ''
        dispatch.save(update_fields=['status', 'finished_at', 'updated_by', 'error_summary', 'updated_at'])

    @staticmethod
    def build_dispatch_payload(*, dispatch):
        items = BotConversaFlowDispatchItemRepository.list_for_dispatch(dispatch)
        return {
            'dispatch': dispatch,
            'items': items,
            'status_payload': {
                'status': dispatch.status,
                'progress_percent': dispatch.progress_percent,
                'total_items': dispatch.total_items,
                'processed_items': dispatch.processed_items,
                'success_items': dispatch.success_items,
                'failed_items': dispatch.failed_items,
                'is_finished': dispatch.status
                in {
                    BotConversaFlowDispatch.Status.COMPLETED,
                    BotConversaFlowDispatch.Status.COMPLETED_WITH_ERRORS,
                    BotConversaFlowDispatch.Status.FAILED,
                },
                'items': [
                    {
                        'target_name': item.target_name,
                        'target_phone': item.target_phone,
                        'status': item.status,
                        'error_message': item.error_message,
                        'sent_at': item.sent_at.isoformat() if item.sent_at else '',
                    }
                    for item in items
                ],
            },
        }
