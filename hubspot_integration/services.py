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
from people.services import PersonService


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
    def build_company_rows(*, organization, include_remote_status=False):
        companies = list(CompanyRepository.list_for_organization(organization))
        remote_summary_by_company_id = {}
        if include_remote_status and companies:
            remote_summary_by_company_id = HubSpotRemoteAssociationService.build_company_summaries(
                organization=organization,
                companies=companies,
            )
        return [
            {
                'company': company,
                'is_synced': bool(company.hubspot_company_id),
                'has_local_deal': bool(company.hubspot_deals.exists()),
                'local_deal_count': company.hubspot_deals.count(),
                'remote_status_checked': include_remote_status,
                'is_remote_synced': remote_summary_by_company_id.get(company.id, {}).get('was_resolved') if include_remote_status else None,
                'has_remote_deal': remote_summary_by_company_id.get(company.id, {}).get('has_remote_deal') if include_remote_status else None,
                'remote_deal_count': remote_summary_by_company_id.get(company.id, {}).get('remote_deal_count', 0),
            }
            for company in companies
        ]

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
    @transaction.atomic
    def create_local_company_with_business(
        *,
        user,
        organization,
        name,
        website='',
        phone='',
        create_deal_now=False,
        deal_name='',
        pipeline=None,
        stage_id='',
        amount='',
    ):
        company = HubSpotCompanyService.create_local_company(
            user=user,
            organization=organization,
            name=name,
            website=website,
            phone=phone,
        )

        if not create_deal_now:
            return company, None

        HubSpotCompanyService.sync_companies(
            user=user,
            organization=organization,
            companies=[company],
        )
        deal = HubSpotDealService.create_deal(
            user=user,
            organization=organization,
            company=company,
            pipeline=pipeline,
            deal_name=deal_name or company.name,
            stage_id=stage_id,
            amount=amount,
            persons=[],
        )
        return company, deal

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

    @staticmethod
    @transaction.atomic
    def sync_companies_with_optional_deal_creation(
        *,
        user,
        organization,
        companies,
        create_deal_now=False,
        pipeline=None,
        stage_id='',
    ):
        synced_companies = HubSpotCompanyService.sync_companies(
            user=user,
            organization=organization,
            companies=companies,
        )
        created_deals = []
        if not create_deal_now:
            return {
                'companies': synced_companies,
                'created_deals': created_deals,
            }

        if pipeline is None:
            raise ValidationError('Selecione um pipeline para criar o negocio.')

        for company in synced_companies:
            created_deals.append(
                HubSpotDealService.create_deal(
                    user=user,
                    organization=organization,
                    company=company,
                    pipeline=pipeline,
                    deal_name=company.name,
                    stage_id=stage_id,
                    amount='',
                    persons=[],
                )
            )

        return {
            'companies': synced_companies,
            'created_deals': created_deals,
        }


class HubSpotContactService:
    @staticmethod
    def build_fallback_phone(*, hubspot_contact_id):
        numeric_seed = ''.join(character for character in str(hubspot_contact_id or '') if character.isdigit())
        if len(numeric_seed) < 9:
            numeric_seed += ''.join(str(ord(character) % 10) for character in str(hubspot_contact_id or ''))
        local_number = f"9{numeric_seed[:8].ljust(8, '0')}"
        return f'+55 11 {local_number[:5]}-{local_number[5:]}'

    @staticmethod
    def build_person_rows(*, organization, include_remote_status=False):
        persons = list(PersonRepository.list_for_organization(organization).prefetch_related('hubspot_deals'))
        remote_summary_by_person_id = {}
        if include_remote_status and persons:
            remote_summary_by_person_id = HubSpotRemoteAssociationService.build_person_summaries(
                organization=organization,
                persons=persons,
            )
        return [
            {
                'person': person,
                'is_synced': bool(person.hubspot_contact_id),
                'has_local_deal': bool(person.hubspot_deals.exists()),
                'local_deal_count': person.hubspot_deals.count(),
                'remote_status_checked': include_remote_status,
                'is_remote_synced': remote_summary_by_person_id.get(person.id, {}).get('was_resolved') if include_remote_status else None,
                'has_remote_deal': remote_summary_by_person_id.get(person.id, {}).get('has_remote_deal') if include_remote_status else None,
                'remote_deal_count': remote_summary_by_person_id.get(person.id, {}).get('remote_deal_count', 0),
            }
            for person in persons
        ]

    @staticmethod
    def build_person_choice_rows(*, organization):
        return [(str(person.public_id), person.full_name) for person in PersonRepository.list_for_organization(organization)]

    @staticmethod
    @transaction.atomic
    def create_local_person(
        *,
        user,
        organization,
        first_name,
        last_name,
        phone,
        email='',
        company=None,
        deal=None,
    ):
        HubSpotAuthorizationService.ensure_operator_access(user=user, organization=organization)

        resolved_company = company
        if deal is not None:
            if deal.organization_id != organization.id:
                raise ValidationError('O negocio selecionado nao pertence a organizacao ativa.')
            if resolved_company is None:
                resolved_company = deal.company
            elif deal.company_id != resolved_company.id:
                raise ValidationError('A pessoa precisa pertencer a mesma empresa do negocio selecionado.')

        person = PersonService.create_person(
            user=user,
            organization=organization,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            company=resolved_company,
        )

        if deal is not None:
            HubSpotDealService.attach_person_to_deal(
                user=user,
                organization=organization,
                deal=deal,
                person=person,
            )
        return person

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


class HubSpotRemoteAssociationService:
    @staticmethod
    def _resolve_remote_company(client, *, company):
        if company.hubspot_company_id:
            return {
                'remote_company_id': company.hubspot_company_id,
                'was_resolved': True,
            }

        remote_company = client.search_company_by_name_or_website(
            name=company.name,
            website=company.website,
        )
        if not remote_company:
            return {
                'remote_company_id': '',
                'was_resolved': False,
            }

        return {
            'remote_company_id': remote_company['hubspot_company_id'],
            'was_resolved': True,
        }

    @staticmethod
    def _resolve_remote_person(client, *, person):
        if person.hubspot_contact_id:
            return {
                'remote_contact_id': person.hubspot_contact_id,
                'was_resolved': True,
            }

        if not person.email:
            return {
                'remote_contact_id': '',
                'was_resolved': False,
            }

        remote_contact = client.search_contact_by_email(email=person.email)
        if not remote_contact:
            return {
                'remote_contact_id': '',
                'was_resolved': False,
            }

        return {
            'remote_contact_id': remote_contact['hubspot_contact_id'],
            'was_resolved': True,
        }

    @staticmethod
    def build_company_summaries(*, organization, companies):
        client = HubSpotInstallationService.build_client(organization=organization)
        summaries = {}
        for company in companies:
            resolved = HubSpotRemoteAssociationService._resolve_remote_company(client, company=company)
            remote_company_id = resolved['remote_company_id']
            if not remote_company_id:
                summaries[company.id] = {
                    'remote_company_id': '',
                    'was_resolved': False,
                    'has_remote_deal': False,
                    'remote_deal_count': 0,
                    'remote_deal_ids': [],
                }
                continue

            deal_summary = client.get_company_deal_summary(company_id=remote_company_id)
            summaries[company.id] = {
                'remote_company_id': remote_company_id,
                'was_resolved': resolved['was_resolved'],
                'has_remote_deal': bool(deal_summary['deal_count']),
                'remote_deal_count': deal_summary['deal_count'],
                'remote_deal_ids': deal_summary['deal_ids'],
            }
        return summaries

    @staticmethod
    def build_person_summaries(*, organization, persons):
        client = HubSpotInstallationService.build_client(organization=organization)
        summaries = {}
        for person in persons:
            resolved = HubSpotRemoteAssociationService._resolve_remote_person(client, person=person)
            remote_contact_id = resolved['remote_contact_id']
            if not remote_contact_id:
                summaries[person.id] = {
                    'remote_contact_id': '',
                    'was_resolved': False,
                    'has_remote_deal': False,
                    'remote_deal_count': 0,
                    'remote_deal_ids': [],
                }
                continue

            deal_summary = client.get_contact_deal_summary(contact_id=remote_contact_id)
            summaries[person.id] = {
                'remote_contact_id': remote_contact_id,
                'was_resolved': resolved['was_resolved'],
                'has_remote_deal': bool(deal_summary['deal_count']),
                'remote_deal_count': deal_summary['deal_count'],
                'remote_deal_ids': deal_summary['deal_ids'],
            }
        return summaries

    @staticmethod
    def build_selected_company_conflicts(*, organization, companies):
        summaries = HubSpotRemoteAssociationService.build_company_summaries(
            organization=organization,
            companies=companies,
        )
        conflicts = []
        for company in companies:
            summary = summaries.get(company.id, {})
            if summary.get('has_remote_deal'):
                conflicts.append(
                    {
                        'company': company,
                        'remote_company_id': summary.get('remote_company_id', ''),
                        'remote_deal_count': summary.get('remote_deal_count', 0),
                    }
                )
        return conflicts


class HubSpotPipelineService:
    @staticmethod
    def build_stage_rows(*, organization):
        stage_rows = []
        for pipeline in HubSpotPipelineRepository.list_for_organization(organization):
            for stage in (pipeline.raw_payload or {}).get('stages') or []:
                stage_id = str(stage.get('id') or '').strip()
                if not stage_id:
                    continue
                stage_rows.append(
                    {
                        'pipeline_public_id': str(pipeline.public_id),
                        'pipeline_name': pipeline.name,
                        'stage_id': stage_id,
                        'stage_name': (stage.get('label') or stage_id).strip(),
                    }
                )
        return stage_rows

    @staticmethod
    def build_stage_choices(*, organization):
        return [
            (row['stage_id'], f"{row['pipeline_name']} - {row['stage_name']}")
            for row in HubSpotPipelineService.build_stage_rows(organization=organization)
        ]

    @staticmethod
    def build_stage_map(*, organization):
        stage_map = {}
        for row in HubSpotPipelineService.build_stage_rows(organization=organization):
            stage_map.setdefault(row['pipeline_public_id'], set()).add(row['stage_id'])
        return stage_map

    @staticmethod
    def build_stage_label_map(*, organization):
        return {
            row['stage_id']: row['stage_name']
            for row in HubSpotPipelineService.build_stage_rows(organization=organization)
        }

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
    def build_deal_option_rows(*, organization, query=''):
        deals = HubSpotDealRepository.search_for_organization(
            organization,
            query=query,
            limit=20,
        )
        return [
            {
                'value': str(deal.public_id),
                'label': f'{deal.name} | {deal.company.name}',
            }
            for deal in deals
        ]

    @staticmethod
    def list_remote_deals(*, organization):
        client = HubSpotInstallationService.build_client(organization=organization)
        local_deals = list(HubSpotDealRepository.list_for_organization(organization))
        pipeline_names = {
            pipeline.hubspot_pipeline_id: pipeline.name
            for pipeline in HubSpotPipelineRepository.list_for_organization(organization)
        }
        stage_names = HubSpotPipelineService.build_stage_label_map(organization=organization)
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
                    'pipeline_name': pipeline_names.get(remote_deal['pipeline_id'], remote_deal['pipeline_id']),
                    'stage_name': stage_names.get(remote_deal['stage_id'], remote_deal['stage_id']),
                    'linked_deal': local_by_hubspot_deal_id.get(remote_deal['hubspot_deal_id']),
                }
            )
        return remote_deals

    @staticmethod
    @transaction.atomic
    def create_deal(*, user, organization, company, pipeline, deal_name, stage_id, amount='', persons=None):
        installation = HubSpotInstallationService.get_installation(organization=organization)
        HubSpotAuthorizationService.ensure_operator_access(user=user, organization=organization)
        if company.organization_id != organization.id:
            raise ValidationError('A empresa selecionada não pertence à organização ativa.')
        if pipeline.organization_id != organization.id:
            raise ValidationError('O pipeline selecionado não pertence à organização ativa.')
        if not company.hubspot_company_id:
            raise ValidationError('Sincronize a empresa com o HubSpot antes de criar um negocio.')

        stage_map = HubSpotPipelineService.build_stage_map(organization=organization)
        valid_stage_ids = stage_map.get(str(pipeline.public_id), set())
        stage_id = str(stage_id or '').strip()
        if not stage_id or stage_id not in valid_stage_ids:
            raise ValidationError('Selecione uma coluna valida para o pipeline informado.')

        resolved_persons = []
        seen_person_ids = set()
        source_persons = (
            persons
            if persons is not None
            else [person for person in PersonRepository.list_for_organization(organization) if person.company_id == company.id]
        )
        for person in source_persons:
            if person.organization_id != organization.id:
                raise ValidationError('Uma ou mais pessoas selecionadas nao pertencem a organizacao ativa.')
            if person.company_id != company.id:
                raise ValidationError('Todas as pessoas do negocio precisam pertencer a empresa selecionada.')
            if person.id in seen_person_ids:
                continue
            seen_person_ids.add(person.id)
            resolved_persons.append(person)

        contact_ids = [person.hubspot_contact_id for person in resolved_persons if person.hubspot_contact_id]

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
        if resolved_persons:
            deal.persons.set(resolved_persons)
        HubSpotSyncLogRepository.create(
            organization=organization,
            installation=installation,
            company=company,
            deal=deal,
            actor=user,
            entity_type=HubSpotSyncLog.EntityType.DEAL,
            outcome=HubSpotSyncLog.Outcome.SUCCESS,
            message='Negocio criado no HubSpot.',
            remote_payload=remote_deal['raw_payload'],
        )
        return deal

    @staticmethod
    @transaction.atomic
    def attach_person_to_deal(*, user, organization, deal, person):
        installation = HubSpotInstallationService.get_installation(organization=organization)
        HubSpotAuthorizationService.ensure_operator_access(user=user, organization=organization)
        if deal.organization_id != organization.id:
            raise ValidationError('O negocio selecionado nao pertence a organizacao ativa.')
        if person.organization_id != organization.id:
            raise ValidationError('A pessoa selecionada nao pertence a organizacao ativa.')

        if person.company_id is None:
            person.company = deal.company
            person.updated_by = user
            person.save(update_fields=['company', 'updated_by', 'updated_at'])
        elif person.company_id != deal.company_id:
            raise ValidationError('A pessoa precisa estar vinculada a mesma empresa do negocio selecionado.')

        if not deal.company.hubspot_company_id:
            HubSpotCompanyService.sync_companies(
                user=user,
                organization=organization,
                companies=[deal.company],
            )

        if not person.hubspot_contact_id:
            HubSpotContactService.sync_people(
                user=user,
                organization=organization,
                persons=[person],
            )
            person = PersonRepository.get_for_organization_and_public_id(organization, person.public_id)

        if deal.hubspot_deal_id and person.hubspot_contact_id:
            client = HubSpotInstallationService.build_client(organization=organization)
            client.associate_contact_to_deal(
                contact_id=person.hubspot_contact_id,
                deal_id=deal.hubspot_deal_id,
            )

        deal.persons.add(person)
        HubSpotSyncLogRepository.create(
            organization=organization,
            installation=installation,
            company=deal.company,
            person=person,
            deal=deal,
            actor=user,
            entity_type=HubSpotSyncLog.EntityType.DEAL,
            outcome=HubSpotSyncLog.Outcome.SUCCESS,
            message='Pessoa vinculada ao negocio no HubSpot.',
            remote_payload={
                'hubspot_deal_id': deal.hubspot_deal_id,
                'hubspot_contact_id': person.hubspot_contact_id,
            },
        )
        return deal
