from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from common.encryption import build_email_lookup, normalize_email_address
from common.matching import (
    build_company_indexes,
    build_person_indexes,
    match_company,
    match_person,
    normalize_text,
)
from common.phone import format_phone_display, normalize_phone
from companies.models import Company
from companies.repositories import CompanyRepository
from companies.services import CompanyService
from hubspot_integration.client import HubSpotClient
from hubspot_integration.constants import HUBSPOT_APP_CODE
from hubspot_integration.exceptions import HubSpotConfigurationError
from hubspot_integration.models import HubSpotDeal, HubSpotSyncLog
from hubspot_integration.repositories import (
    HubSpotDealRepository,
    HubSpotPipelineRepository,
    HubSpotSyncLogRepository,
)
from integrations.repositories import AppCatalogRepository, AppCredentialRepository, AppInstallationRepository
from organizations.repositories import MembershipRepository
from people.models import Person
from people.repositories import PersonRepository


class HubSpotAuthorizationService:
    @staticmethod
    def ensure_membership(*, user, organization):
        membership = MembershipRepository.get_for_user_and_organization(user, organization)
        if membership is None:
            raise PermissionDenied('Você não faz parte da organização ativa.')
        return membership

    @staticmethod
    def ensure_operator_access(*, user, organization):
        membership = HubSpotAuthorizationService.ensure_membership(user=user, organization=organization)
        if not membership.can_manage_integrations:
            raise PermissionDenied('Somente proprietários e administradores podem operar ações do HubSpot.')
        return membership


class HubSpotInstallationService:
    @staticmethod
    def get_installation(*, organization):
        app = AppCatalogRepository.get_by_code(HUBSPOT_APP_CODE)
        if app is None:
            raise HubSpotConfigurationError('O HubSpot não está registrado no catálogo de aplicativos.')

        installation = AppInstallationRepository.get_for_organization_and_app(organization, app)
        if installation is None or not installation.is_installed:
            raise ValidationError('Instale o HubSpot para a organização ativa antes de usar este módulo.')
        return installation

    @staticmethod
    def get_api_key(*, organization):
        installation = HubSpotInstallationService.get_installation(organization=organization)
        credential = AppCredentialRepository.get_current_api_key(installation)
        if credential is None:
            raise HubSpotConfigurationError('Configure a chave do HubSpot antes de usar este módulo.')
        return installation, credential.secret_value

    @staticmethod
    def build_client(*, organization):
        _installation, api_key = HubSpotInstallationService.get_api_key(organization=organization)
        return HubSpotClient(api_key=api_key)


class HubSpotBulkPreparationService:
    @staticmethod
    def prepare_company(company):
        company.hubspot_company_id = (company.hubspot_company_id or '').strip()
        company.name = (company.name or '').strip()
        company.website = (company.website or '').strip()
        normalized_phone = normalize_phone(company.phone) if company.phone else ''
        company.normalized_phone = normalized_phone
        company.phone = format_phone_display(normalized_phone) if normalized_phone else ''
        return company

    @staticmethod
    def prepare_person(person):
        person.bot_conversa_id = (person.bot_conversa_id or '').strip() or None
        person.hubspot_contact_id = (person.hubspot_contact_id or '').strip()
        normalized_phone = normalize_phone(person.phone)
        person.normalized_phone = normalized_phone
        person.phone = format_phone_display(normalized_phone)
        normalized_email = normalize_email_address(person.email) if person.email else ''
        person.email = normalized_email
        person.email_lookup = build_email_lookup(normalized_email) if normalized_email else ''
        person.first_name = (person.first_name or '').strip()
        person.last_name = (person.last_name or '').strip()
        return person


class HubSpotDashboardService:
    @staticmethod
    def build_summary(*, organization):
        installation = HubSpotInstallationService.get_installation(organization=organization)
        companies = list(CompanyRepository.list_for_organization(organization))
        persons = list(PersonRepository.list_for_organization(organization))
        pipelines = list(HubSpotPipelineRepository.list_for_organization(organization))
        deals = list(HubSpotDealRepository.list_for_organization(organization))

        return {
            'installation': installation,
            'company_count': len(companies),
            'synced_company_count': len([company for company in companies if company.hubspot_company_id]),
            'synced_person_count': len([person for person in persons if person.hubspot_contact_id]),
            'pipeline_count': len(pipelines),
            'deal_count': len(deals),
            'recent_sync_logs': HubSpotSyncLogRepository.list_recent_for_organization(organization, limit=5),
            'recent_deals': deals[:5],
        }


class HubSpotCompanyService:
    @staticmethod
    def build_company_rows(*, organization):
        companies = list(CompanyRepository.list_for_organization(organization))
        return [{'company': company, 'is_synced': bool(company.hubspot_company_id)} for company in companies]

    @staticmethod
    def build_company_choice_rows(*, organization):
        return [(str(company.public_id), company.name) for company in CompanyRepository.list_for_organization(organization)]

    @staticmethod
    @transaction.atomic
    def create_local_company(*, user, organization, name, website='', phone=''):
        HubSpotAuthorizationService.ensure_operator_access(user=user, organization=organization)
        return CompanyService.create_company(
            user=user,
            organization=organization,
            name=name,
            website=website,
            phone=phone,
        )

    @staticmethod
    def list_remote_companies(*, organization):
        client = HubSpotInstallationService.build_client(organization=organization)
        local_companies = list(CompanyRepository.list_for_organization(organization))
        company_indexes = build_company_indexes(companies=local_companies)

        remote_companies = []
        for remote_company in client.list_companies():
            remote_companies.append(
                {
                    **remote_company,
                    'linked_company': match_company(
                        remote_company=remote_company,
                        company_indexes=company_indexes,
                    ),
                }
            )
        return remote_companies

    @staticmethod
    @transaction.atomic
    def sync_companies(*, user, organization, companies):
        installation = HubSpotInstallationService.get_installation(organization=organization)
        HubSpotAuthorizationService.ensure_operator_access(user=user, organization=organization)
        client = HubSpotInstallationService.build_client(organization=organization)

        unique_companies = []
        seen_company_ids = set()
        for company in companies:
            if company.organization_id != organization.id:
                raise ValidationError('Uma ou mais empresas selecionadas não pertencem à organização ativa.')
            if company.id in seen_company_ids:
                continue
            unique_companies.append(company)
            seen_company_ids.add(company.id)

        if not unique_companies:
            raise ValidationError('Selecione pelo menos uma empresa para sincronizar.')

        synced_at = timezone.now()
        companies_to_update = []
        sync_logs = []

        for company in unique_companies:
            remote_company = client.create_or_get_company(
                name=company.name,
                website=company.website,
                phone=company.phone,
            )
            company.hubspot_company_id = remote_company['hubspot_company_id']
            company.updated_by = user
            company.updated_at = synced_at
            companies_to_update.append(company)
            sync_logs.append(
                HubSpotSyncLog(
                    organization=organization,
                    installation=installation,
                    company=company,
                    actor=user,
                    entity_type=HubSpotSyncLog.EntityType.COMPANY,
                    outcome=HubSpotSyncLog.Outcome.SUCCESS,
                    message='Empresa sincronizada com o HubSpot.',
                    remote_payload=remote_company['raw_payload'],
                )
            )

        CompanyRepository.bulk_update(companies_to_update, ['hubspot_company_id', 'updated_by', 'updated_at'])
        HubSpotSyncLogRepository.bulk_create(sync_logs)
        return unique_companies

    @staticmethod
    @transaction.atomic
    def import_remote_companies(*, user, organization, remote_companies):
        HubSpotAuthorizationService.ensure_operator_access(user=user, organization=organization)
        local_companies = list(CompanyRepository.list_for_organization(organization))
        company_indexes = build_company_indexes(companies=local_companies)
        synced_at = timezone.now()

        companies_to_create = []
        companies_to_update = []
        persisted_companies = []

        for remote_company in remote_companies:
            matched_company = match_company(
                remote_company=remote_company,
                company_indexes=company_indexes,
            )
            if matched_company is not None:
                changed = False
                if not matched_company.hubspot_company_id and remote_company['hubspot_company_id']:
                    matched_company.hubspot_company_id = remote_company['hubspot_company_id']
                    changed = True
                if not matched_company.website and remote_company.get('website'):
                    matched_company.website = remote_company['website']
                    changed = True
                if not matched_company.phone and remote_company.get('phone'):
                    matched_company.phone = remote_company['phone']
                    changed = True
                if changed:
                    HubSpotBulkPreparationService.prepare_company(matched_company)
                    matched_company.updated_by = user
                    matched_company.updated_at = synced_at
                    companies_to_update.append(matched_company)
                persisted_companies.append(matched_company)
                company_indexes = build_company_indexes(companies=local_companies)
                continue

            company = Company(
                organization=organization,
                hubspot_company_id=remote_company['hubspot_company_id'],
                name=remote_company['name'],
                website=remote_company.get('website', ''),
                phone=remote_company.get('phone', ''),
                created_by=user,
                updated_by=user,
            )
            HubSpotBulkPreparationService.prepare_company(company)
            companies_to_create.append(company)
            persisted_companies.append(company)
            local_companies.append(company)
            company_indexes = build_company_indexes(companies=local_companies)

        if companies_to_create:
            CompanyRepository.bulk_create(companies_to_create)
        if companies_to_update:
            CompanyRepository.bulk_update(companies_to_update, ['hubspot_company_id', 'website', 'phone', 'updated_by', 'updated_at'])

        return persisted_companies


class HubSpotContactService:
    @staticmethod
    def build_fallback_phone(*, hubspot_contact_id):
        numeric_seed = ''.join(character for character in str(hubspot_contact_id or '') if character.isdigit())
        if len(numeric_seed) < 9:
            numeric_seed += ''.join(str(ord(character) % 10) for character in str(hubspot_contact_id or ''))
        local_number = f"9{numeric_seed[:8].ljust(8, '0')}"
        return f'+55 11 {local_number[:5]}-{local_number[5:]}'

    @staticmethod
    def build_person_rows(*, organization):
        persons = list(PersonRepository.list_for_organization(organization))
        return [{'person': person, 'is_synced': bool(person.hubspot_contact_id)} for person in persons]

    @staticmethod
    def build_person_choice_rows(*, organization):
        return [(str(person.public_id), person.full_name) for person in PersonRepository.list_for_organization(organization)]

    @staticmethod
    def resolve_local_company_for_contact(*, organization, company_name='', company_hubspot_id=''):
        if company_hubspot_id:
            company = CompanyRepository.get_for_organization_and_hubspot_company_id(organization, company_hubspot_id)
            if company is not None:
                return company

        normalized_company_name = normalize_text(company_name)
        if not normalized_company_name:
            return None

        for company in CompanyRepository.list_for_organization(organization):
            if normalize_text(company.name) == normalized_company_name:
                return company
        return None

    @staticmethod
    def list_remote_contacts(*, organization):
        client = HubSpotInstallationService.build_client(organization=organization)
        local_persons = list(PersonRepository.list_for_organization(organization))
        person_indexes = build_person_indexes(persons=local_persons)

        remote_contacts = []
        for remote_contact in client.list_contacts():
            remote_contacts.append(
                {
                    **remote_contact,
                    'linked_person': match_person(
                        remote_contact=remote_contact,
                        person_indexes=person_indexes,
                        integration_key='hubspot',
                    ),
                }
            )
        return remote_contacts

    @staticmethod
    @transaction.atomic
    def sync_contact_company_links(*, user, organization):
        HubSpotAuthorizationService.ensure_operator_access(user=user, organization=organization)
        remote_contacts = HubSpotContactService.list_remote_contacts(organization=organization)
        synced_at = timezone.now()
        persons_to_update_by_id = {}

        for remote_contact in remote_contacts:
            linked_person = remote_contact.get('linked_person')
            if linked_person is None:
                continue

            company = HubSpotContactService.resolve_local_company_for_contact(
                organization=organization,
                company_name=remote_contact.get('company_name', ''),
                company_hubspot_id=remote_contact.get('company_hubspot_id', ''),
            )
            if company is None:
                continue
            if linked_person.organization_id != organization.id:
                continue
            if linked_person.company_id == company.id:
                continue

            linked_person.company = company
            linked_person.updated_by = user
            linked_person.updated_at = synced_at
            persons_to_update_by_id[linked_person.id] = linked_person

        persons_to_update = list(persons_to_update_by_id.values())
        if persons_to_update:
            PersonRepository.bulk_update(persons_to_update, ['company', 'updated_by', 'updated_at'])
        return persons_to_update

    @staticmethod
    @transaction.atomic
    def sync_people(*, user, organization, persons):
        installation = HubSpotInstallationService.get_installation(organization=organization)
        HubSpotAuthorizationService.ensure_operator_access(user=user, organization=organization)
        client = HubSpotInstallationService.build_client(organization=organization)

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

        synced_at = timezone.now()
        persons_to_update = []
        sync_logs = []

        for person in unique_persons:
            company_id = person.company.hubspot_company_id if person.company and person.company.hubspot_company_id else ''
            remote_contact = client.create_or_get_contact(
                first_name=person.first_name,
                last_name=person.last_name,
                email=person.email,
                phone=person.phone,
                company_id=company_id,
            )
            person.hubspot_contact_id = remote_contact['hubspot_contact_id']
            person.updated_by = user
            person.updated_at = synced_at
            persons_to_update.append(person)
            sync_logs.append(
                HubSpotSyncLog(
                    organization=organization,
                    installation=installation,
                    person=person,
                    actor=user,
                    entity_type=HubSpotSyncLog.EntityType.PERSON,
                    outcome=HubSpotSyncLog.Outcome.SUCCESS,
                    message='Pessoa sincronizada com o HubSpot.',
                    remote_payload=remote_contact['raw_payload'],
                )
            )

        PersonRepository.bulk_update(persons_to_update, ['hubspot_contact_id', 'updated_by', 'updated_at'])
        HubSpotSyncLogRepository.bulk_create(sync_logs)
        return unique_persons

    @staticmethod
    @transaction.atomic
    def import_remote_contacts(*, user, organization, remote_contacts):
        HubSpotAuthorizationService.ensure_operator_access(user=user, organization=organization)
        local_persons = list(PersonRepository.list_for_organization(organization))
        person_indexes = build_person_indexes(persons=local_persons)
        synced_at = timezone.now()

        persons_to_create = []
        persons_to_update_by_key = {}
        persisted_persons = []
        staged_persons_by_hubspot_id = {
            person.hubspot_contact_id: person
            for person in local_persons
            if person.hubspot_contact_id
        }
        staged_persons_by_email_lookup = {
            person.email_lookup: person
            for person in local_persons
            if person.email_lookup
        }
        staged_persons_by_phone = {
            person.normalized_phone: person
            for person in local_persons
            if person.normalized_phone
        }

        for remote_contact in remote_contacts:
            remote_hubspot_contact_id = (remote_contact.get('hubspot_contact_id') or '').strip()
            company = HubSpotContactService.resolve_local_company_for_contact(
                organization=organization,
                company_name=remote_contact.get('company_name', ''),
                company_hubspot_id=remote_contact.get('company_hubspot_id', ''),
            )
            normalized_email = normalize_email_address(remote_contact.get('email', '')) if remote_contact.get('email') else ''
            email_lookup = build_email_lookup(normalized_email) if normalized_email else ''
            resolved_phone = remote_contact.get('phone') or ''
            try:
                normalized_phone = normalize_phone(resolved_phone)
            except ValidationError:
                resolved_phone = ''
                normalized_phone = ''
            resolved_phone = resolved_phone or HubSpotContactService.build_fallback_phone(
                hubspot_contact_id=remote_contact.get('hubspot_contact_id', ''),
            )
            normalized_phone = normalized_phone or normalize_phone(resolved_phone)
            resolved_first_name = (remote_contact.get('first_name') or '').strip() or 'Contato'
            resolved_last_name = (remote_contact.get('last_name') or '').strip() or 'HubSpot'
            matched_person = (
                staged_persons_by_hubspot_id.get(remote_hubspot_contact_id)
                or staged_persons_by_email_lookup.get(email_lookup)
                or staged_persons_by_phone.get(normalized_phone)
                or match_person(
                    remote_contact=remote_contact,
                    person_indexes=person_indexes,
                    integration_key='hubspot',
                )
            )

            if matched_person is not None:
                changed = False
                if not matched_person.hubspot_contact_id and remote_hubspot_contact_id:
                    matched_person.hubspot_contact_id = remote_hubspot_contact_id
                    changed = True
                if not matched_person.email and normalized_email:
                    matched_person.email = normalized_email
                    changed = True
                if not matched_person.company and company is not None:
                    matched_person.company = company
                    changed = True
                if changed:
                    HubSpotBulkPreparationService.prepare_person(matched_person)
                    matched_person.updated_by = user
                    matched_person.updated_at = synced_at
                    staged_persons_by_hubspot_id[matched_person.hubspot_contact_id] = matched_person
                    if matched_person.email_lookup:
                        staged_persons_by_email_lookup[matched_person.email_lookup] = matched_person
                    if matched_person.normalized_phone:
                        staged_persons_by_phone[matched_person.normalized_phone] = matched_person
                    if matched_person.pk:
                        persons_to_update_by_key[matched_person.pk] = matched_person
                persisted_persons.append(matched_person)
                continue

            person = Person(
                organization=organization,
                first_name=resolved_first_name,
                last_name=resolved_last_name,
                email=normalized_email,
                phone=resolved_phone,
                hubspot_contact_id=remote_hubspot_contact_id,
                company=company,
                created_by=user,
                updated_by=user,
            )
            HubSpotBulkPreparationService.prepare_person(person)
            persons_to_create.append(person)
            persisted_persons.append(person)
            local_persons.append(person)
            if person.hubspot_contact_id:
                staged_persons_by_hubspot_id[person.hubspot_contact_id] = person
            if person.email_lookup:
                staged_persons_by_email_lookup[person.email_lookup] = person
            if person.normalized_phone:
                staged_persons_by_phone[person.normalized_phone] = person
            person_indexes = build_person_indexes(persons=local_persons)

        if persons_to_create:
            PersonRepository.bulk_create(persons_to_create)
        persons_to_update = list(persons_to_update_by_key.values())
        if persons_to_update:
            PersonRepository.bulk_update(persons_to_update, ['hubspot_contact_id', 'email', 'email_lookup', 'company', 'updated_by', 'updated_at'])

        return persisted_persons


class HubSpotPipelineService:
    @staticmethod
    @transaction.atomic
    def refresh_pipelines(*, user, organization):
        installation = HubSpotInstallationService.get_installation(organization=organization)
        HubSpotAuthorizationService.ensure_operator_access(user=user, organization=organization)
        client = HubSpotInstallationService.build_client(organization=organization)
        synced_at = timezone.now()
        refreshed_pipelines = []

        for remote_pipeline in client.list_deal_pipelines():
            pipeline_cache = HubSpotPipelineRepository.get_for_organization_and_hubspot_pipeline_id(
                organization,
                remote_pipeline['hubspot_pipeline_id'],
            )
            if pipeline_cache is None:
                pipeline_cache = HubSpotPipelineRepository.create(
                    organization=organization,
                    installation=installation,
                    hubspot_pipeline_id=remote_pipeline['hubspot_pipeline_id'],
                    name=remote_pipeline['name'],
                    object_type=remote_pipeline['object_type'],
                    raw_payload=remote_pipeline['raw_payload'],
                    last_synced_at=synced_at,
                )
            else:
                pipeline_cache.name = remote_pipeline['name']
                pipeline_cache.object_type = remote_pipeline['object_type']
                pipeline_cache.raw_payload = remote_pipeline['raw_payload']
                pipeline_cache.last_synced_at = synced_at
                pipeline_cache.save(update_fields=['name', 'object_type', 'raw_payload', 'last_synced_at', 'updated_at'])
            refreshed_pipelines.append(pipeline_cache)

        HubSpotSyncLogRepository.create(
            organization=organization,
            installation=installation,
            actor=user,
            entity_type=HubSpotSyncLog.EntityType.PIPELINE,
            outcome=HubSpotSyncLog.Outcome.SUCCESS,
            message='Pipelines do HubSpot atualizados.',
            remote_payload={'count': len(refreshed_pipelines)},
        )
        return refreshed_pipelines


class HubSpotDealService:
    @staticmethod
    def list_remote_deals(*, organization):
        client = HubSpotInstallationService.build_client(organization=organization)
        local_deals = list(HubSpotDealRepository.list_for_organization(organization))
        local_by_hubspot_deal_id = {
            deal.hubspot_deal_id: deal
            for deal in local_deals
            if deal.hubspot_deal_id
        }

        remote_deals = []
        for remote_deal in client.list_deals():
            remote_deals.append(
                {
                    **remote_deal,
                    'linked_deal': local_by_hubspot_deal_id.get(remote_deal['hubspot_deal_id']),
                }
            )
        return remote_deals

    @staticmethod
    @transaction.atomic
    def create_deal(*, user, organization, company, pipeline, deal_name, amount=''):
        installation = HubSpotInstallationService.get_installation(organization=organization)
        HubSpotAuthorizationService.ensure_operator_access(user=user, organization=organization)
        if company.organization_id != organization.id:
            raise ValidationError('A empresa selecionada não pertence à organização ativa.')
        if pipeline.organization_id != organization.id:
            raise ValidationError('O pipeline selecionado não pertence à organização ativa.')
        if not company.hubspot_company_id:
            raise ValidationError('Sincronize a empresa com o HubSpot antes de criar um deal.')

        persons = list(PersonRepository.list_for_organization(organization))
        contact_ids = [
            person.hubspot_contact_id
            for person in persons
            if person.company_id == company.id and person.hubspot_contact_id
        ]
        stage_id = ''
        pipeline_stages = (pipeline.raw_payload or {}).get('stages') or []
        if pipeline_stages:
            stage_id = str(pipeline_stages[0].get('id') or '')

        client = HubSpotInstallationService.build_client(organization=organization)
        remote_deal = client.create_deal(
            name=deal_name,
            pipeline_id=pipeline.hubspot_pipeline_id,
            stage_id=stage_id,
            company_id=company.hubspot_company_id,
            contact_ids=contact_ids,
            amount=amount,
        )
        deal = HubSpotDealRepository.create(
            organization=organization,
            installation=installation,
            company=company,
            pipeline=pipeline,
            hubspot_deal_id=remote_deal['hubspot_deal_id'],
            name=deal_name,
            amount=amount,
            stage_id=stage_id,
            sync_status=HubSpotDeal.SyncStatus.SYNCED,
            raw_payload=remote_deal['raw_payload'],
            created_by=user,
            updated_by=user,
        )
        HubSpotSyncLogRepository.create(
            organization=organization,
            installation=installation,
            company=company,
            deal=deal,
            actor=user,
            entity_type=HubSpotSyncLog.EntityType.DEAL,
            outcome=HubSpotSyncLog.Outcome.SUCCESS,
            message='Deal criado no HubSpot.',
            remote_payload=remote_deal['raw_payload'],
        )
        return deal
