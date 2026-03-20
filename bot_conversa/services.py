import random
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from bot_conversa.client import BotConversaClient
from bot_conversa.constants import BOT_CONVERSA_APP_CODE, DEFAULT_DISPATCH_BATCH_SIZE
from bot_conversa.exceptions import BotConversaApiError, BotConversaConfigurationError
from bot_conversa.forms import BotConversaDispatchCreateForm
from bot_conversa.models import (
    BotConversaContact,
    BotConversaFlowCache,
    BotConversaFlowDispatch,
    BotConversaFlowDispatchItem,
    BotConversaPersonTag,
    BotConversaSyncLog,
    BotConversaTag,
)
from bot_conversa.repositories import (
    BotConversaContactRepository,
    BotConversaFlowCacheRepository,
    BotConversaFlowDispatchItemRepository,
    BotConversaFlowDispatchRepository,
    BotConversaPersonTagRepository,
    BotConversaSyncLogRepository,
    BotConversaTagRepository,
)
from common.matching import build_person_indexes, match_person
from common.phone import format_phone_display, normalize_phone
from integrations.repositories import AppCatalogRepository, AppCredentialRepository, AppInstallationRepository
from organizations.repositories import MembershipRepository
from people.models import Person
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
            'tag_count': BotConversaTagRepository.list_for_organization(organization).count(),
            'recent_dispatches': recent_dispatches,
            'recent_sync_logs': recent_sync_logs,
        }


class BotConversaDispatchWorkspaceService:
    @staticmethod
    def build_person_choices(*, organization, only_unsent=False, tag_public_ids=None):
        persons = list(PersonRepository.list_for_organization(organization))
        selected_tag_ids = []

        if tag_public_ids:
            selected_tag_ids = [
                tag.id
                for tag in BotConversaTagRepository.list_for_organization_and_public_ids(
                    organization,
                    tag_public_ids,
                )
            ]

        if selected_tag_ids:
            tagged_person_ids = set(
                BotConversaTagService.list_person_ids_for_tags(
                    organization=organization,
                    tag_ids=selected_tag_ids,
                )
            )
            persons = [person for person in persons if person.id in tagged_person_ids]

        if only_unsent:
            successful_person_ids = set(
                BotConversaFlowDispatchItemRepository.list_success_person_ids_for_organization(
                    organization,
                )
            )
            persons = [person for person in persons if person.id not in successful_person_ids]

        return [
            (str(person.public_id), f'{person.full_name} - {person.phone}')
            for person in persons
        ]

    @staticmethod
    def build_flow_choices(*, organization):
        return [
            (str(flow.public_id), flow.name)
            for flow in BotConversaFlowCacheRepository.list_selectable_for_organization(organization)
        ]

    @staticmethod
    def build_tag_choices(*, organization):
        return BotConversaTagService.build_tag_choice_rows(organization=organization)

    @staticmethod
    def build_dispatch_form(*, organization, selected_tag_public_ids=None, **kwargs):
        person_choices = BotConversaDispatchWorkspaceService.build_person_choices(
            organization=organization,
            tag_public_ids=selected_tag_public_ids,
        )
        return BotConversaDispatchCreateForm(
            flow_choices=BotConversaDispatchWorkspaceService.build_flow_choices(
                organization=organization,
            ),
            person_choices=person_choices,
            tag_choices=BotConversaDispatchWorkspaceService.build_tag_choices(
                organization=organization,
            ),
            **kwargs,
        )


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
    @transaction.atomic
    def create_person_with_tags(*, user, organization, first_name, last_name, phone, email='', tags=None):
        person = BotConversaPeopleService.create_person(
            user=user,
            organization=organization,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
        )
        resolved_tags = list(tags or [])
        if resolved_tags:
            for tag in resolved_tags:
                BotConversaTagService.ensure_tag_access(organization=organization, tag=tag)
            BotConversaTagService.assign_tag_to_people(
                user=user,
                organization=organization,
                tag=resolved_tags[0],
                persons=[person],
            )
            for tag in resolved_tags[1:]:
                BotConversaTagService.assign_tag_to_people(
                    user=user,
                    organization=organization,
                    tag=tag,
                    persons=[person],
                )
        return person

    @staticmethod
    def build_person_rows(*, organization):
        persons = list(PersonRepository.list_for_organization(organization))
        synced_contacts = list(BotConversaContactRepository.list_for_organization(organization))
        person_tag_links = list(BotConversaPersonTagRepository.list_for_organization(organization))
        contact_by_person_id = {contact.person_id: contact for contact in synced_contacts}
        tags_by_person_id = {}
        for person_tag_link in person_tag_links:
            tags_by_person_id.setdefault(person_tag_link.person_id, []).append(person_tag_link.tag)

        person_rows = []
        for person in persons:
            contact_link = contact_by_person_id.get(person.id)
            person_rows.append(
                {
                    'person': person,
                    'contact_link': contact_link,
                    'tags': tags_by_person_id.get(person.id, []),
                    'is_synced': bool(contact_link and contact_link.sync_status == BotConversaContact.SyncStatus.SYNCED),
                }
            )

        return person_rows


class BotConversaBulkPreparationService:
    @staticmethod
    def prepare_contact_link(contact_link):
        normalized_phone = normalize_phone(contact_link.phone)
        contact_link.normalized_phone = normalized_phone
        contact_link.phone = format_phone_display(normalized_phone)
        contact_link.external_subscriber_id = (contact_link.external_subscriber_id or '').strip()
        contact_link.external_name = (contact_link.external_name or '').strip()
        return contact_link


class BotConversaTagService:
    @staticmethod
    def sync_tag_cache_from_payloads(*, organization, installation, remote_tags, synced_at):
        existing_tags = {
            tag.external_tag_id: tag
            for tag in BotConversaTagRepository.list_for_organization(organization)
        }
        tags_to_create = []
        tags_to_update = []

        for remote_tag in remote_tags:
            external_tag_id = remote_tag['external_tag_id']
            tag = existing_tags.get(external_tag_id)
            if tag is None:
                tags_to_create.append(
                    BotConversaTag(
                        organization=organization,
                        installation=installation,
                        external_tag_id=external_tag_id,
                        name=remote_tag['name'],
                        last_synced_at=synced_at,
                        raw_payload=remote_tag['raw_payload'],
                    )
                )
                continue

            tag.name = remote_tag['name']
            tag.last_synced_at = synced_at
            tag.raw_payload = remote_tag['raw_payload']
            tags_to_update.append(tag)

        if tags_to_create:
            BotConversaTagRepository.bulk_create(tags_to_create)
        if tags_to_update:
            BotConversaTagRepository.bulk_update(
                tags_to_update,
                ['name', 'last_synced_at', 'raw_payload', 'updated_at'],
            )

        return list(BotConversaTagRepository.list_for_organization(organization))

    @staticmethod
    @transaction.atomic
    def refresh_tags(*, user, organization):
        installation = BotConversaInstallationService.get_installation(organization=organization)
        BotConversaAuthorizationService.ensure_operator_access(user=user, organization=organization)
        client = BotConversaInstallationService.build_client(organization=organization)

        synced_at = timezone.now()
        return BotConversaTagService.sync_tag_cache_from_payloads(
            organization=organization,
            installation=installation,
            remote_tags=client.list_tags(),
            synced_at=synced_at,
        )

    @staticmethod
    def build_tag_rows(*, organization):
        person_tag_links = list(BotConversaPersonTagRepository.list_for_organization(organization))
        counts_by_tag_id = {}
        for person_tag_link in person_tag_links:
            counts_by_tag_id[person_tag_link.tag_id] = counts_by_tag_id.get(person_tag_link.tag_id, 0) + 1

        return [
            {
                'tag': tag,
                'person_count': counts_by_tag_id.get(tag.id, 0),
            }
            for tag in BotConversaTagRepository.list_for_organization(organization)
        ]

    @staticmethod
    def build_tag_choice_rows(*, organization):
        return [(str(tag.public_id), tag.name) for tag in BotConversaTagRepository.list_for_organization(organization)]

    @staticmethod
    def list_person_ids_for_tags(*, organization, tag_ids):
        if not tag_ids:
            return []
        return BotConversaPersonTagRepository.list_person_ids_for_organization_and_tag_ids(
            organization,
            tag_ids,
        )

    @staticmethod
    def sync_remote_tags_for_person(
        *,
        user,
        organization,
        installation,
        person,
        contact_link,
        remote_contact,
        available_tags_by_name,
        synced_at,
    ):
        remote_tag_names = remote_contact.get('tag_names') or []
        keep_tag_ids = []
        person_tags_to_create = []
        person_tags_to_update = []

        for tag_name in remote_tag_names:
            tag = available_tags_by_name.get(tag_name.strip().lower())
            if tag is None:
                continue

            keep_tag_ids.append(tag.id)
            person_tag_link = BotConversaPersonTagRepository.get_for_organization_and_person_and_tag(
                organization,
                person,
                tag,
            )

            if person_tag_link is None:
                person_tags_to_create.append(
                    BotConversaPersonTag(
                        organization=organization,
                        installation=installation,
                        person=person,
                        tag=tag,
                        contact_link=contact_link,
                        external_subscriber_id=contact_link.external_subscriber_id,
                        sync_status=BotConversaPersonTag.SyncStatus.SYNCED,
                        last_synced_at=synced_at,
                        remote_payload=remote_contact['raw_payload'],
                        created_by=user,
                        updated_by=user,
                    )
                )
                continue

            person_tag_link.contact_link = contact_link
            person_tag_link.external_subscriber_id = contact_link.external_subscriber_id
            person_tag_link.sync_status = BotConversaPersonTag.SyncStatus.SYNCED
            person_tag_link.last_synced_at = synced_at
            person_tag_link.last_error_message = ''
            person_tag_link.remote_payload = remote_contact['raw_payload']
            person_tag_link.updated_by = user
            person_tags_to_update.append(person_tag_link)

        if person_tags_to_create:
            BotConversaPersonTagRepository.bulk_create(person_tags_to_create)
        if person_tags_to_update:
            BotConversaPersonTagRepository.bulk_update(
                person_tags_to_update,
                [
                    'contact_link',
                    'external_subscriber_id',
                    'sync_status',
                    'last_synced_at',
                    'last_error_message',
                    'remote_payload',
                    'updated_by',
                    'updated_at',
                ],
            )

        BotConversaPersonTagRepository.delete_for_organization_and_person_excluding_tag_ids(
            organization,
            person,
            keep_tag_ids,
        )

    @staticmethod
    def ensure_tag_access(*, organization, tag):
        if tag.organization_id != organization.id:
            raise PermissionDenied('A etiqueta selecionada nao pertence a organizacao ativa.')

    @staticmethod
    @transaction.atomic
    def assign_tag_to_people(*, user, organization, tag, persons):
        installation = BotConversaInstallationService.get_installation(organization=organization)
        BotConversaAuthorizationService.ensure_operator_access(user=user, organization=organization)
        BotConversaTagService.ensure_tag_access(organization=organization, tag=tag)
        client = BotConversaInstallationService.build_client(organization=organization)
        synced_at = timezone.now()

        unique_persons = []
        seen_person_ids = set()
        for person in persons:
            if person.organization_id != organization.id:
                raise ValidationError('Uma ou mais pessoas selecionadas nao pertencem a organizacao ativa.')
            if person.id in seen_person_ids:
                continue
            unique_persons.append(person)
            seen_person_ids.add(person.id)

        if not unique_persons:
            raise ValidationError('Selecione pelo menos uma pessoa para vincular a etiqueta.')

        person_tags_to_create = []
        person_tags_to_update = []

        for person in unique_persons:
            person_tag_link = BotConversaPersonTagRepository.get_for_organization_and_person_and_tag(
                organization,
                person,
                tag,
            )
            contact_link = BotConversaContactSyncService.ensure_remote_contact(
                user=user,
                organization=organization,
                person=person,
            )
            response_payload = {'raw_payload': person_tag_link.remote_payload if person_tag_link else {}}
            if (
                person_tag_link is None
                or person_tag_link.external_subscriber_id != contact_link.external_subscriber_id
                or person_tag_link.sync_status != BotConversaPersonTag.SyncStatus.SYNCED
            ):
                response_payload = client.add_tag_to_subscriber(
                    subscriber_id=contact_link.external_subscriber_id,
                    tag_id=tag.external_tag_id,
                )
            if person_tag_link is None:
                person_tag_link = BotConversaPersonTag(
                    organization=organization,
                    installation=installation,
                    person=person,
                    tag=tag,
                    contact_link=contact_link,
                    external_subscriber_id=contact_link.external_subscriber_id,
                    sync_status=BotConversaPersonTag.SyncStatus.SYNCED,
                    last_synced_at=synced_at,
                    remote_payload=response_payload['raw_payload'],
                    created_by=user,
                    updated_by=user,
                )
                person_tags_to_create.append(person_tag_link)
            else:
                person_tag_link.contact_link = contact_link
                person_tag_link.external_subscriber_id = contact_link.external_subscriber_id
                person_tag_link.sync_status = BotConversaPersonTag.SyncStatus.SYNCED
                person_tag_link.last_synced_at = synced_at
                person_tag_link.last_error_message = ''
                person_tag_link.remote_payload = response_payload['raw_payload']
                person_tag_link.updated_by = user
                person_tag_link.updated_at = synced_at
                person_tags_to_update.append(person_tag_link)

        if person_tags_to_create:
            BotConversaPersonTagRepository.bulk_create(person_tags_to_create)
        if person_tags_to_update:
            BotConversaPersonTagRepository.bulk_update(
                person_tags_to_update,
                [
                    'contact_link',
                    'external_subscriber_id',
                    'sync_status',
                    'last_synced_at',
                    'last_error_message',
                    'remote_payload',
                    'updated_by',
                    'updated_at',
                ],
            )

        return unique_persons


class BotConversaTagPreflightService:
    @staticmethod
    def list_untagged_people(*, organization, persons):
        unique_persons = []
        seen_person_ids = set()
        tagged_person_ids = {
            person_tag.person_id
            for person_tag in BotConversaPersonTagRepository.list_for_organization(organization)
            if person_tag.person_id is not None
        }

        for person in persons:
            if person.organization_id != organization.id or person.id in seen_person_ids:
                continue
            seen_person_ids.add(person.id)
            if person.id not in tagged_person_ids:
                unique_persons.append(person)

        return unique_persons

    @staticmethod
    def apply_tags_by_public_ids(*, user, organization, persons, tag_public_ids):
        resolved_tags = list(
            BotConversaTagRepository.list_for_organization_and_public_ids(
                organization,
                tag_public_ids,
            )
        )
        for tag in resolved_tags:
            BotConversaTagService.assign_tag_to_people(
                user=user,
                organization=organization,
                tag=tag,
                persons=persons,
            )
        return resolved_tags


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
        synced_at = timezone.now()
        available_tags_by_name = {
            tag.name.strip().lower(): tag
            for tag in BotConversaTagService.sync_tag_cache_from_payloads(
                organization=organization,
                installation=installation,
                remote_tags=client.list_tags(),
                synced_at=synced_at,
            )
        }
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
        BotConversaTagService.sync_remote_tags_for_person(
            user=user,
            organization=organization,
            installation=installation,
            person=person,
            contact_link=contact_link,
            remote_contact=remote_contact,
            available_tags_by_name=available_tags_by_name,
            synced_at=synced_at,
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
    @transaction.atomic
    def sync_people(*, user, organization, persons):
        installation = BotConversaInstallationService.get_installation(organization=organization)
        BotConversaAuthorizationService.ensure_operator_access(user=user, organization=organization)
        client = BotConversaInstallationService.build_client(organization=organization)
        synced_at = timezone.now()
        available_tags_by_name = {
            tag.name.strip().lower(): tag
            for tag in BotConversaTagService.sync_tag_cache_from_payloads(
                organization=organization,
                installation=installation,
                remote_tags=client.list_tags(),
                synced_at=synced_at,
            )
        }

        unique_persons = []
        seen_person_ids = set()
        for person in persons:
            if person.organization_id != organization.id:
                raise ValidationError('Uma ou mais pessoas selecionadas não pertencem à organização ativa.')
            if person.id in seen_person_ids:
                continue
            unique_persons.append(person)
            seen_person_ids.add(person.id)

        if not unique_persons:
            raise ValidationError('Selecione pelo menos uma pessoa para sincronizar.')

        existing_contact_links = {
            contact_link.person_id: contact_link
            for contact_link in BotConversaContactRepository.list_for_organization(organization)
        }
        persons_to_update = []
        contact_links_to_create = []
        contact_links_to_update = []
        sync_logs = []
        remote_contacts_by_person_id = {}

        for person in unique_persons:
            remote_phone = person.normalized_phone
            remote_contact = client.search_contact_by_phone(phone=remote_phone)
            action = BotConversaSyncLog.Action.LINK
            if remote_contact is None:
                remote_contact = client.create_contact(
                    first_name=person.first_name,
                    last_name=person.last_name,
                    phone=remote_phone,
                )
                action = BotConversaSyncLog.Action.CREATE
            remote_contacts_by_person_id[person.id] = remote_contact

            person.bot_conversa_id = remote_contact['external_subscriber_id']
            person.updated_by = user
            person.updated_at = synced_at
            persons_to_update.append(person)

            contact_link = existing_contact_links.get(person.id)
            if contact_link is None:
                contact_link = BotConversaContact(
                    organization=organization,
                    installation=installation,
                    person=person,
                    external_subscriber_id=remote_contact['external_subscriber_id'],
                    external_name=remote_contact['name'] or person.full_name,
                    phone=remote_contact['phone'] or person.phone,
                    sync_status=BotConversaContact.SyncStatus.SYNCED,
                    last_synced_at=synced_at,
                    remote_payload=remote_contact['raw_payload'],
                    created_by=user,
                    updated_by=user,
                )
                BotConversaBulkPreparationService.prepare_contact_link(contact_link)
                contact_links_to_create.append(contact_link)
                log_contact_link = None
            else:
                contact_link.external_subscriber_id = remote_contact['external_subscriber_id']
                contact_link.external_name = remote_contact['name'] or person.full_name
                contact_link.phone = remote_contact['phone'] or person.phone
                contact_link.sync_status = BotConversaContact.SyncStatus.SYNCED
                contact_link.last_synced_at = synced_at
                contact_link.last_error_message = ''
                contact_link.remote_payload = remote_contact['raw_payload']
                contact_link.updated_by = user
                contact_link.updated_at = synced_at
                BotConversaBulkPreparationService.prepare_contact_link(contact_link)
                contact_links_to_update.append(contact_link)
                log_contact_link = contact_link

            sync_logs.append(
                BotConversaSyncLog(
                    organization=organization,
                    installation=installation,
                    person=person,
                    contact_link=log_contact_link,
                    actor=user,
                    action=action,
                    outcome=BotConversaSyncLog.Outcome.SUCCESS,
                    message='Contato vinculado com sucesso.',
                    remote_payload=remote_contact['raw_payload'],
                )
            )

        PersonRepository.bulk_update(persons_to_update, ['bot_conversa_id', 'updated_by', 'updated_at'])
        if contact_links_to_create:
            BotConversaContactRepository.bulk_create(contact_links_to_create)
            created_contact_links_by_person_id = {
                contact_link.person_id: contact_link
                for contact_link in contact_links_to_create
                if contact_link.person_id
            }
            for sync_log in sync_logs:
                if sync_log.contact_link_id is None and sync_log.person_id in created_contact_links_by_person_id:
                    sync_log.contact_link = created_contact_links_by_person_id[sync_log.person_id]
        if contact_links_to_update:
            BotConversaContactRepository.bulk_update(
                contact_links_to_update,
                [
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
                ],
            )
        contact_links_by_person_id = {
            contact_link.person_id: contact_link
            for contact_link in BotConversaContactRepository.list_for_organization(organization)
        }
        for person in unique_persons:
            BotConversaTagService.sync_remote_tags_for_person(
                user=user,
                organization=organization,
                installation=installation,
                person=person,
                contact_link=contact_links_by_person_id[person.id],
                remote_contact=remote_contacts_by_person_id[person.id],
                available_tags_by_name=available_tags_by_name,
                synced_at=synced_at,
            )
        BotConversaSyncLogRepository.bulk_create(sync_logs)
        return unique_persons

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
        person_indexes = build_person_indexes(persons=persons)
        local_by_subscriber_id = {
            contact.external_subscriber_id: contact
            for contact in local_contacts
        }

        remote_contacts = []
        for remote_contact in client.list_contacts(search=search):
            linked_contact = local_by_subscriber_id.get(remote_contact['external_subscriber_id'])
            linked_person = match_person(
                remote_contact=remote_contact,
                person_indexes=person_indexes,
                integration_key='bot_conversa',
            )
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
    def save_contacts_to_crm(*, user, organization, remote_contacts):
        installation = BotConversaInstallationService.get_installation(organization=organization)
        BotConversaAuthorizationService.ensure_operator_access(user=user, organization=organization)
        persons = list(PersonRepository.list_for_organization(organization))
        person_indexes = build_person_indexes(persons=persons)
        existing_contact_links = {
            contact_link.external_subscriber_id: contact_link
            for contact_link in BotConversaContactRepository.list_for_organization(organization)
        }
        synced_at = timezone.now()

        persons_to_create = []
        persons_to_update = []
        contact_links_to_create = []
        contact_links_to_update = []
        sync_logs = []
        processed_persons = []

        for remote_contact in remote_contacts:
            normalized_subscriber_id = (remote_contact.get('external_subscriber_id') or '').strip()
            if not normalized_subscriber_id:
                continue

            matched_person = match_person(
                remote_contact=remote_contact,
                person_indexes=person_indexes,
                integration_key='bot_conversa',
            )
            resolved_first_name, resolved_last_name = BotConversaRemoteContactService.resolve_contact_name(
                first_name=remote_contact.get('first_name', ''),
                last_name=remote_contact.get('last_name', ''),
                external_name=remote_contact.get('name', ''),
            )

            if matched_person is None:
                matched_person = Person(
                    organization=organization,
                    first_name=resolved_first_name,
                    last_name=resolved_last_name,
                    phone=remote_contact['phone'],
                    bot_conversa_id=normalized_subscriber_id,
                    created_by=user,
                    updated_by=user,
                )
                matched_person.normalized_phone = normalize_phone(matched_person.phone)
                matched_person.phone = format_phone_display(matched_person.normalized_phone)
                persons_to_create.append(matched_person)
                persons.append(matched_person)
                person_indexes = build_person_indexes(persons=persons)
            else:
                if not matched_person.bot_conversa_id:
                    matched_person.bot_conversa_id = normalized_subscriber_id
                    matched_person.updated_by = user
                    matched_person.updated_at = synced_at
                    persons_to_update.append(matched_person)

            processed_persons.append(matched_person)
            contact_link = existing_contact_links.get(normalized_subscriber_id)
            if contact_link is None:
                contact_link = BotConversaContact(
                    organization=organization,
                    installation=installation,
                    person=matched_person,
                    external_subscriber_id=normalized_subscriber_id,
                    external_name=remote_contact.get('name') or matched_person.full_name,
                    phone=remote_contact['phone'],
                    sync_status=BotConversaContact.SyncStatus.SYNCED,
                    last_synced_at=synced_at,
                    remote_payload=remote_contact.get('raw_payload', {}),
                    created_by=user,
                    updated_by=user,
                )
                BotConversaBulkPreparationService.prepare_contact_link(contact_link)
                contact_links_to_create.append(contact_link)
                existing_contact_links[normalized_subscriber_id] = contact_link
                log_contact_link = None
            else:
                contact_link.person = matched_person
                contact_link.external_name = remote_contact.get('name') or matched_person.full_name
                contact_link.phone = remote_contact['phone']
                contact_link.sync_status = BotConversaContact.SyncStatus.SYNCED
                contact_link.last_synced_at = synced_at
                contact_link.last_error_message = ''
                contact_link.remote_payload = remote_contact.get('raw_payload', {})
                contact_link.updated_by = user
                contact_link.updated_at = synced_at
                BotConversaBulkPreparationService.prepare_contact_link(contact_link)
                contact_links_to_update.append(contact_link)
                log_contact_link = contact_link

            sync_logs.append(
                BotConversaSyncLog(
                    organization=organization,
                    installation=installation,
                    person=matched_person,
                    contact_link=log_contact_link,
                    actor=user,
                    action=BotConversaSyncLog.Action.CREATE if matched_person in persons_to_create else BotConversaSyncLog.Action.LINK,
                    outcome=BotConversaSyncLog.Outcome.SUCCESS,
                    message='Contato remoto salvo no CRM.',
                    remote_payload=remote_contact.get('raw_payload', {}),
                )
            )

        if persons_to_create:
            PersonRepository.bulk_create(persons_to_create)
            for contact_link in contact_links_to_create:
                contact_link.person_id = contact_link.person.id
            for sync_log in sync_logs:
                if sync_log.person_id is None and sync_log.person is not None:
                    sync_log.person_id = sync_log.person.id
        if persons_to_update:
            PersonRepository.bulk_update(persons_to_update, ['bot_conversa_id', 'updated_by', 'updated_at'])
        if contact_links_to_create:
            BotConversaContactRepository.bulk_create(contact_links_to_create)
            created_contact_links_by_person_id = {
                contact_link.person_id: contact_link
                for contact_link in contact_links_to_create
                if contact_link.person_id
            }
            for sync_log in sync_logs:
                if sync_log.contact_link_id is None and sync_log.person_id in created_contact_links_by_person_id:
                    sync_log.contact_link = created_contact_links_by_person_id[sync_log.person_id]
        if contact_links_to_update:
            BotConversaContactRepository.bulk_update(
                contact_links_to_update,
                [
                    'person',
                    'external_name',
                    'phone',
                    'normalized_phone',
                    'sync_status',
                    'last_synced_at',
                    'last_error_message',
                    'remote_payload',
                    'updated_by',
                    'updated_at',
                ],
            )
        BotConversaSyncLogRepository.bulk_create(sync_logs)
        return processed_persons

    @staticmethod
    @transaction.atomic
    def save_contact_to_crm(*, user, organization, external_subscriber_id, phone, first_name='', last_name='', external_name=''):
        existing_person = PersonRepository.get_for_organization_and_bot_conversa_id(organization, external_subscriber_id)
        saved_persons = BotConversaRemoteContactService.save_contacts_to_crm(
            user=user,
            organization=organization,
            remote_contacts=[
                {
                    'external_subscriber_id': external_subscriber_id,
                    'first_name': first_name,
                    'last_name': last_name,
                    'name': external_name,
                    'phone': phone,
                    'status': 'active',
                    'raw_payload': {},
                }
            ],
        )
        if not saved_persons:
            raise ValidationError('Nao foi possivel salvar o contato remoto no CRM. Verifique subscriber e telefone.')
        person = saved_persons[0]
        return {
            'person': person,
            'contact_link': BotConversaContactRepository.get_for_organization_and_person(organization, person),
            'created_person': existing_person is None,
            'linked_existing_person': existing_person is not None and existing_person.pk == person.pk,
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
    STALE_RUNNING_ITEM_TIMEOUT_SECONDS = 300

    @staticmethod
    @transaction.atomic
    def create_dispatch(
        *,
        user,
        organization,
        flow_cache,
        persons,
        tags=None,
        min_delay_seconds=0,
        max_delay_seconds=0,
    ):
        installation = BotConversaInstallationService.get_installation(organization=organization)
        BotConversaAuthorizationService.ensure_operator_access(user=user, organization=organization)
        BotConversaDispatchService.ensure_flow_access(organization=organization, flow_cache=flow_cache)

        resolved_tags = list(tags or [])
        tag_person_ids = set()
        if resolved_tags:
            for tag in resolved_tags:
                BotConversaTagService.ensure_tag_access(organization=organization, tag=tag)
            tag_person_ids = set(
                BotConversaPersonTagRepository.list_person_ids_for_organization_and_tag_ids(
                    organization,
                    [tag.id for tag in resolved_tags],
                )
            )

        unique_persons = []
        seen_person_ids = set()
        for person in persons:
            if person.organization_id != organization.id:
                raise PermissionDenied('Uma ou mais pessoas selecionadas não pertencem à organização ativa.')
            if person.id not in seen_person_ids:
                unique_persons.append(person)
                seen_person_ids.add(person.id)

        if tag_person_ids:
            tagged_persons = list(
                PersonRepository.list_for_organization(organization).filter(id__in=tag_person_ids)
            )
            for person in tagged_persons:
                if person.id not in seen_person_ids:
                    unique_persons.append(person)
                    seen_person_ids.add(person.id)

        if not unique_persons:
            raise ValidationError('Selecione pelo menos uma pessoa ou uma etiqueta para o disparo.')

        if min_delay_seconds < 0 or max_delay_seconds < 0:
            raise ValidationError('Os delays do disparo nao podem ser negativos.')
        if max_delay_seconds < min_delay_seconds:
            raise ValidationError('O delay maximo nao pode ser menor que o delay minimo.')

        dispatch = BotConversaFlowDispatchRepository.create(
            organization=organization,
            installation=installation,
            flow=flow_cache,
            external_flow_id=flow_cache.external_flow_id,
            flow_name=flow_cache.name,
            status=BotConversaFlowDispatch.Status.PENDING,
            total_items=len(unique_persons),
            min_delay_seconds=min_delay_seconds,
            max_delay_seconds=max_delay_seconds,
            next_process_after=timezone.now(),
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
    def process_pending_items(
        *,
        user,
        organization,
        dispatch,
        batch_size=DEFAULT_DISPATCH_BATCH_SIZE,
        skip_authorization=False,
    ):
        if not skip_authorization:
            BotConversaAuthorizationService.ensure_operator_access(user=user, organization=organization)
        if dispatch.organization_id != organization.id:
            raise PermissionDenied('O disparo selecionado não pertence à organização ativa.')

        if dispatch.status in {
            BotConversaFlowDispatch.Status.PAUSED,
            BotConversaFlowDispatch.Status.COMPLETED,
            BotConversaFlowDispatch.Status.COMPLETED_WITH_ERRORS,
            BotConversaFlowDispatch.Status.FAILED,
        }:
            return dispatch

        client = BotConversaInstallationService.build_client(organization=organization)
        current_time = timezone.now()

        if dispatch.next_process_after and dispatch.next_process_after > current_time:
            return dispatch

        if dispatch.status == BotConversaFlowDispatch.Status.PENDING:
            dispatch.status = BotConversaFlowDispatch.Status.RUNNING
            dispatch.started_at = dispatch.started_at or timezone.now()
            if user is not None:
                dispatch.updated_by = user
            dispatch.save(update_fields=['status', 'started_at', 'updated_by', 'updated_at'])

        BotConversaDispatchService.requeue_stale_running_items(dispatch=dispatch)

        effective_batch_size = 1 if dispatch.max_delay_seconds > 0 else batch_size
        pending_items = list(
            BotConversaFlowDispatchItemRepository.list_pending_for_dispatch(
                dispatch,
                limit=effective_batch_size,
            )
        )

        if not pending_items:
            BotConversaDispatchService.refresh_dispatch_counters(dispatch=dispatch, user=user)
            return dispatch

        for item in pending_items:
            attempt_time = timezone.now()
            claimed_rows = BotConversaFlowDispatchItemRepository.claim_for_processing(
                item,
                attempted_at=attempt_time,
            )
            if not claimed_rows:
                continue

            item.status = BotConversaFlowDispatchItem.Status.RUNNING
            item.last_attempt_at = attempt_time
            item.attempt_count += 1

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

        BotConversaDispatchService.schedule_next_processing(dispatch=dispatch, user=user)
        BotConversaDispatchService.refresh_dispatch_counters(dispatch=dispatch, user=user)
        return dispatch

    @staticmethod
    def requeue_stale_running_items(*, dispatch):
        cutoff_time = timezone.now() - timedelta(seconds=BotConversaDispatchService.STALE_RUNNING_ITEM_TIMEOUT_SECONDS)
        return BotConversaFlowDispatchItemRepository.requeue_stale_running_for_dispatch(
            dispatch,
            cutoff_time=cutoff_time,
        )

    @staticmethod
    @transaction.atomic
    def pause_dispatch(*, user, organization, dispatch):
        BotConversaAuthorizationService.ensure_operator_access(user=user, organization=organization)
        if dispatch.organization_id != organization.id:
            raise PermissionDenied('O disparo selecionado nÃ£o pertence Ã  organizaÃ§Ã£o ativa.')
        if dispatch.status in {
            BotConversaFlowDispatch.Status.COMPLETED,
            BotConversaFlowDispatch.Status.COMPLETED_WITH_ERRORS,
            BotConversaFlowDispatch.Status.FAILED,
        }:
            raise ValidationError('Nao e possivel pausar um disparo ja finalizado.')
        if dispatch.status == BotConversaFlowDispatch.Status.PAUSED:
            return dispatch

        dispatch.status = BotConversaFlowDispatch.Status.PAUSED
        dispatch.next_process_after = None
        dispatch.updated_by = user
        dispatch.save(update_fields=['status', 'next_process_after', 'updated_by', 'updated_at'])
        return dispatch

    @staticmethod
    @transaction.atomic
    def resume_dispatch(*, user, organization, dispatch):
        BotConversaAuthorizationService.ensure_operator_access(user=user, organization=organization)
        if dispatch.organization_id != organization.id:
            raise PermissionDenied('O disparo selecionado nÃ£o pertence Ã  organizaÃ§Ã£o ativa.')
        if dispatch.status in {
            BotConversaFlowDispatch.Status.COMPLETED,
            BotConversaFlowDispatch.Status.COMPLETED_WITH_ERRORS,
            BotConversaFlowDispatch.Status.FAILED,
        }:
            raise ValidationError('Nao e possivel continuar um disparo ja finalizado.')

        dispatch.status = BotConversaFlowDispatch.Status.PENDING
        dispatch.next_process_after = timezone.now()
        dispatch.updated_by = user
        dispatch.save(update_fields=['status', 'next_process_after', 'updated_by', 'updated_at'])
        return dispatch

    @staticmethod
    @transaction.atomic
    def reprocess_running_items(*, user, organization, dispatch):
        BotConversaAuthorizationService.ensure_operator_access(user=user, organization=organization)
        if dispatch.organization_id != organization.id:
            raise PermissionDenied('O disparo selecionado nÃ£o pertence Ã  organizaÃ§Ã£o ativa.')
        if dispatch.status in {
            BotConversaFlowDispatch.Status.COMPLETED,
            BotConversaFlowDispatch.Status.COMPLETED_WITH_ERRORS,
            BotConversaFlowDispatch.Status.FAILED,
        }:
            raise ValidationError('Nao e possivel reprocessar itens de um disparo ja finalizado.')

        requeued_count = BotConversaFlowDispatchItemRepository.requeue_all_running_for_dispatch(dispatch)
        if dispatch.status != BotConversaFlowDispatch.Status.PAUSED:
            dispatch.status = BotConversaFlowDispatch.Status.PENDING
            dispatch.next_process_after = timezone.now()
            dispatch.updated_by = user
            dispatch.save(update_fields=['status', 'next_process_after', 'updated_by', 'updated_at'])
        return requeued_count

    @staticmethod
    def refresh_dispatch_counters(*, dispatch, user):
        items = BotConversaFlowDispatchItemRepository.list_for_dispatch(dispatch)
        processed_items = items.filter(
            status__in=[
                BotConversaFlowDispatchItem.Status.SUCCESS,
                BotConversaFlowDispatchItem.Status.FAILED,
                BotConversaFlowDispatchItem.Status.SKIPPED,
            ]
        ).count()
        success_items = items.filter(status=BotConversaFlowDispatchItem.Status.SUCCESS).count()
        failed_items = items.filter(status=BotConversaFlowDispatchItem.Status.FAILED).count()
        pending_items = items.filter(status=BotConversaFlowDispatchItem.Status.PENDING).count()
        running_items = items.filter(status=BotConversaFlowDispatchItem.Status.RUNNING).count()

        dispatch.processed_items = processed_items
        dispatch.success_items = success_items
        dispatch.failed_items = failed_items
        if user is not None:
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

        if processed_items >= dispatch.total_items and pending_items == 0 and running_items == 0:
            BotConversaDispatchService.finalize_dispatch(dispatch=dispatch, user=user)

    @staticmethod
    def build_next_poll_delay_ms(*, dispatch):
        if dispatch.next_process_after:
            remaining_ms = int((dispatch.next_process_after - timezone.now()).total_seconds() * 1000)
            if remaining_ms > 0:
                return remaining_ms
        if dispatch.max_delay_seconds > 0:
            return dispatch.max_delay_seconds * 1000
        return 1600

    @staticmethod
    def schedule_next_processing(*, dispatch, user=None):
        if dispatch.max_delay_seconds > 0:
            delay_seconds = random.randint(dispatch.min_delay_seconds, dispatch.max_delay_seconds)
            dispatch.next_process_after = timezone.now() + timedelta(seconds=delay_seconds)
        else:
            dispatch.next_process_after = timezone.now()

        if user is not None:
            dispatch.updated_by = user

        dispatch.save(update_fields=['next_process_after', 'updated_by', 'updated_at'])

    @staticmethod
    def finalize_dispatch(*, dispatch, user):
        if dispatch.failed_items and dispatch.success_items:
            dispatch.status = BotConversaFlowDispatch.Status.COMPLETED_WITH_ERRORS
        elif dispatch.failed_items and not dispatch.success_items:
            dispatch.status = BotConversaFlowDispatch.Status.FAILED
        else:
            dispatch.status = BotConversaFlowDispatch.Status.COMPLETED

        dispatch.finished_at = timezone.now()
        dispatch.next_process_after = None
        dispatch.updated_by = user
        dispatch.error_summary = 'Alguns contatos nao puderam receber o fluxo.' if dispatch.failed_items else ''
        dispatch.save(update_fields=['status', 'finished_at', 'next_process_after', 'updated_by', 'error_summary', 'updated_at'])

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
                'next_poll_delay_ms': BotConversaDispatchService.build_next_poll_delay_ms(dispatch=dispatch),
                'is_finished': dispatch.status
                in {
                    BotConversaFlowDispatch.Status.PAUSED,
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


class BotConversaDispatchWorkerService:
    @staticmethod
    def run_cycle(*, limit=20):
        dispatches = list(BotConversaFlowDispatchRepository.list_runnable_dispatches(limit=limit))
        processed_count = 0
        for dispatch in dispatches:
            BotConversaDispatchService.process_pending_items(
                user=dispatch.updated_by or dispatch.created_by,
                organization=dispatch.organization,
                dispatch=dispatch,
                skip_authorization=True,
            )
            processed_count += 1
        return processed_count
