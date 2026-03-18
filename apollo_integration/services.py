import secrets
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apollo_integration.client import ApolloClient
from apollo_integration.constants import APOLLO_APP_CODE, APOLLO_BULK_ENRICH_MAX_BATCH_SIZE
from apollo_integration.exceptions import ApolloApiError, ApolloConfigurationError
from apollo_integration.models import ApolloCompanySyncLog, ApolloPeopleEnrichmentItem, ApolloPeopleEnrichmentJob
from apollo_integration.repositories import (
    ApolloCompanySyncLogRepository,
    ApolloPeopleEnrichmentItemRepository,
    ApolloPeopleEnrichmentJobRepository,
    ApolloUsageSnapshotRepository,
)
from common.encryption import normalize_email_address
from common.matching import build_company_indexes, build_person_indexes, match_company, match_person
from common.phone import format_phone_display, normalize_phone
from companies.models import Company
from companies.repositories import CompanyRepository
from hubspot_integration.services import HubSpotCompanyService
from integrations.repositories import AppCatalogRepository, AppCredentialRepository, AppInstallationRepository
from organizations.repositories import MembershipRepository
from people.models import Person
from people.repositories import PersonRepository


class ApolloAuthorizationService:
    @staticmethod
    def ensure_membership(*, user, organization):
        membership = MembershipRepository.get_for_user_and_organization(user, organization)
        if membership is None:
            raise PermissionDenied('Voce nao faz parte da organizacao ativa.')
        return membership

    @staticmethod
    def ensure_operator_access(*, user, organization):
        membership = ApolloAuthorizationService.ensure_membership(user=user, organization=organization)
        if not membership.can_manage_integrations:
            raise PermissionDenied('Somente proprietarios e administradores podem operar o Apollo.')
        return membership


class ApolloInstallationService:
    @staticmethod
    def get_installation(*, organization):
        app = AppCatalogRepository.get_by_code(APOLLO_APP_CODE)
        if app is None:
            raise ApolloConfigurationError('O Apollo nao esta registrado no catalogo de aplicativos.')

        installation = AppInstallationRepository.get_for_organization_and_app(organization, app)
        if installation is None or not installation.is_installed:
            raise ValidationError('Instale o Apollo para a organizacao ativa antes de usar este modulo.')
        return installation

    @staticmethod
    def get_api_key(*, organization):
        installation = ApolloInstallationService.get_installation(organization=organization)
        credential = AppCredentialRepository.get_current_api_key(installation)
        if credential is None:
            raise ApolloConfigurationError('Configure a chave de API do Apollo antes de usar este modulo.')
        return installation, credential.secret_value

    @staticmethod
    def build_client(*, organization):
        _installation, api_key = ApolloInstallationService.get_api_key(organization=organization)
        return ApolloClient(api_key=api_key)


class ApolloBulkPreparationService:
    @staticmethod
    def prepare_company(company):
        company.apollo_company_id = (company.apollo_company_id or '').strip()
        company.hubspot_company_id = (company.hubspot_company_id or '').strip()
        company.name = (company.name or '').strip()
        company.website = (company.website or '').strip()
        company.email = (company.email or '').strip().lower()
        company.segment = (company.segment or '').strip()
        normalized_phone = normalize_phone(company.phone) if company.phone else ''
        company.normalized_phone = normalized_phone
        company.phone = format_phone_display(normalized_phone) if normalized_phone else ''
        return company

    @staticmethod
    def prepare_person(person):
        person.apollo_person_id = (person.apollo_person_id or '').strip()
        person.hubspot_contact_id = (person.hubspot_contact_id or '').strip()
        person.bot_conversa_id = (person.bot_conversa_id or '').strip() or None
        person.first_name = (person.first_name or '').strip()
        person.last_name = (person.last_name or '').strip()
        normalized_email = normalize_email_address(person.email) if person.email else ''
        person.email = normalized_email
        if person.phone:
            normalized_phone = normalize_phone(person.phone)
            person.normalized_phone = normalized_phone
            person.phone = format_phone_display(normalized_phone)
        else:
            person.normalized_phone = ''
            person.phone = ''
        return person


class ApolloDashboardService:
    @staticmethod
    def build_summary(*, organization):
        installation = ApolloInstallationService.get_installation(organization=organization)
        companies = list(CompanyRepository.list_for_organization(organization))
        usage = ApolloDashboardService.build_usage_snapshot(organization=organization)
        return {
            'installation': installation,
            'company_count': len(companies),
            'synced_company_count': len([company for company in companies if company.apollo_company_id]),
            'recent_sync_logs': ApolloCompanySyncLogRepository.list_recent_for_organization(organization, limit=5),
            'usage': usage,
        }

    @staticmethod
    def build_usage_snapshot(*, organization):
        installation = ApolloInstallationService.get_installation(organization=organization)
        client = ApolloInstallationService.build_client(organization=organization)
        try:
            payload = client.get_usage_stats()
        except ApolloApiError as exc:
            latest_snapshot = ApolloUsageSnapshotRepository.get_latest_for_organization(organization)
            if latest_snapshot is not None:
                return {
                    'available': True,
                    'message': f'{exc} Exibindo o ultimo snapshot salvo.',
                    'raw_payload': latest_snapshot.raw_payload,
                    'credit_summary': ApolloDashboardService.extract_credit_summary(latest_snapshot.raw_payload),
                    'rate_limits': ApolloDashboardService.extract_rate_limits(latest_snapshot.raw_payload),
                    'fetched_at': latest_snapshot.fetched_at,
                    'is_cached': True,
                }
            return {
                'available': False,
                'message': str(exc),
                'raw_payload': {},
                'credit_summary': [],
                'rate_limits': [],
                'fetched_at': None,
                'is_cached': False,
            }

        fetched_at = timezone.now()
        ApolloUsageSnapshotRepository.create(
            organization=organization,
            installation=installation,
            fetched_at=fetched_at,
            raw_payload=payload,
            credits_used=ApolloDashboardService.extract_integer(payload, 'credits_used', 'api_credits_used'),
            credits_remaining=ApolloDashboardService.extract_integer(payload, 'credits_remaining', 'api_credits_remaining'),
            rate_limit_per_minute=ApolloDashboardService.extract_nested_integer(
                payload,
                ('limits', 'per_minute'),
                ('rate_limits', 'per_minute'),
            ),
            rate_limit_per_hour=ApolloDashboardService.extract_nested_integer(
                payload,
                ('limits', 'per_hour'),
                ('rate_limits', 'per_hour'),
            ),
            rate_limit_per_day=ApolloDashboardService.extract_nested_integer(
                payload,
                ('limits', 'per_day'),
                ('rate_limits', 'per_day'),
            ),
        )

        return {
            'available': True,
            'message': '',
            'raw_payload': payload,
            'credit_summary': ApolloDashboardService.extract_credit_summary(payload),
            'rate_limits': ApolloDashboardService.extract_rate_limits(payload),
            'fetched_at': fetched_at,
            'is_cached': False,
        }

    @staticmethod
    def extract_integer(payload, *keys):
        for key in keys:
            value = payload.get(key)
            try:
                return int(value) if value not in (None, '') else None
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def extract_nested_integer(payload, *paths):
        for path in paths:
            current = payload
            for key in path:
                if not isinstance(current, dict):
                    current = None
                    break
                current = current.get(key)
            try:
                return int(current) if current not in (None, '') else None
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def extract_credit_summary(payload):
        summary = []
        for key in ('credits_remaining', 'credits_used', 'api_credits_remaining', 'api_credits_used'):
            if key in payload:
                summary.append({'label': key, 'value': payload.get(key)})
        return summary

    @staticmethod
    def extract_rate_limits(payload):
        candidates = []
        for key, value in payload.items():
            normalized_key = str(key).lower()
            if 'limit' in normalized_key or 'usage' in normalized_key:
                candidates.append({'label': key, 'value': value})
        return candidates[:8]


class ApolloCompanyService:
    @staticmethod
    def build_company_rows(*, organization):
        companies = list(CompanyRepository.list_for_organization(organization))
        return [
            {
                'company': company,
                'is_apollo_synced': bool(company.apollo_company_id),
                'is_hubspot_synced': bool(company.hubspot_company_id),
            }
            for company in companies
        ]

    @staticmethod
    def build_company_choice_rows(*, organization):
        return [(str(company.public_id), company.name) for company in CompanyRepository.list_for_organization(organization)]

    @staticmethod
    def build_search_payload(*, filters):
        payload = {
            'page': filters.get('page') or 1,
            'per_page': filters.get('per_page') or 25,
        }
        if filters.get('q_organization_name'):
            payload['q_organization_name'] = filters['q_organization_name']
        if filters.get('q_organization_domains'):
            payload['q_organization_domains_list'] = filters['q_organization_domains']
        if filters.get('organization_locations'):
            payload['organization_locations'] = filters['organization_locations']
        if filters.get('organization_industries'):
            payload['organization_industries'] = filters['organization_industries']
        if filters.get('organization_num_employees_ranges'):
            payload['organization_num_employees_ranges'] = filters['organization_num_employees_ranges']
        return payload

    @staticmethod
    def list_remote_companies(*, organization, filters):
        client = ApolloInstallationService.build_client(organization=organization)
        local_companies = list(CompanyRepository.list_for_organization(organization))
        company_indexes = build_company_indexes(companies=local_companies)
        payload = ApolloCompanyService.build_search_payload(filters=filters)
        search_result = client.search_organizations(payload=payload)

        remote_companies = []
        for remote_company in search_result['organizations']:
            linked_company = match_company(remote_company=remote_company, company_indexes=company_indexes)
            remote_companies.append(
                {
                    **remote_company,
                    'linked_company': linked_company,
                    'is_saved_in_crm': linked_company is not None,
                    'is_synced_with_hubspot': bool(linked_company and linked_company.hubspot_company_id),
                }
            )

        return {
            'companies': remote_companies,
            'pagination': search_result.get('pagination') or {},
            'payload': payload,
        }

    @staticmethod
    @transaction.atomic
    def import_remote_companies(*, user, organization, remote_companies):
        installation = ApolloInstallationService.get_installation(organization=organization)
        ApolloAuthorizationService.ensure_operator_access(user=user, organization=organization)
        local_companies = list(CompanyRepository.list_for_organization(organization))
        company_indexes = build_company_indexes(companies=local_companies)
        synced_at = timezone.now()

        companies_to_create = []
        companies_to_update = []
        persisted_companies = []
        sync_logs = []
        new_company_log_pairs = []

        for remote_company in remote_companies:
            matched_company = match_company(remote_company=remote_company, company_indexes=company_indexes)
            if matched_company is not None:
                changed = False
                if not matched_company.apollo_company_id and remote_company['apollo_company_id']:
                    matched_company.apollo_company_id = remote_company['apollo_company_id']
                    company_indexes['by_apollo_id'][matched_company.apollo_company_id] = matched_company
                    changed = True
                if not matched_company.website and remote_company.get('website'):
                    matched_company.website = remote_company['website']
                    changed = True
                if not matched_company.email and remote_company.get('email'):
                    matched_company.email = remote_company['email']
                    changed = True
                if not matched_company.phone and remote_company.get('phone'):
                    matched_company.phone = remote_company['phone']
                    changed = True
                if not matched_company.segment and remote_company.get('segment'):
                    matched_company.segment = remote_company['segment']
                    changed = True
                if matched_company.employee_count is None and remote_company.get('employee_count') is not None:
                    matched_company.employee_count = remote_company['employee_count']
                    changed = True
                if changed:
                    ApolloBulkPreparationService.prepare_company(matched_company)
                    matched_company.updated_by = user
                    matched_company.updated_at = synced_at
                    companies_to_update.append(matched_company)
                persisted_companies.append(matched_company)
                sync_logs.append(
                    ApolloCompanySyncLog(
                        organization=organization,
                        installation=installation,
                        company=matched_company,
                        actor=user,
                        action=ApolloCompanySyncLog.Action.IMPORT,
                        outcome=ApolloCompanySyncLog.Outcome.SUCCESS,
                        message='Empresa do Apollo vinculada ao CRM existente.',
                        remote_payload=remote_company.get('raw_payload', {}),
                    )
                )
                continue

            company = Company(
                organization=organization,
                apollo_company_id=remote_company['apollo_company_id'],
                name=remote_company['name'],
                website=remote_company.get('website', ''),
                email=remote_company.get('email', ''),
                phone=remote_company.get('phone', ''),
                segment=remote_company.get('segment', ''),
                employee_count=remote_company.get('employee_count'),
                created_by=user,
                updated_by=user,
            )
            ApolloBulkPreparationService.prepare_company(company)
            companies_to_create.append(company)
            local_companies.append(company)
            company_indexes = build_company_indexes(companies=local_companies)
            persisted_companies.append(company)
            new_company_log_pairs.append((company, remote_company))

        if companies_to_create:
            CompanyRepository.bulk_create(companies_to_create)
        if companies_to_update:
            CompanyRepository.bulk_update(
                companies_to_update,
                ['apollo_company_id', 'website', 'email', 'phone', 'segment', 'employee_count', 'updated_by', 'updated_at'],
            )

        for company, remote_company in new_company_log_pairs:
            sync_logs.append(
                ApolloCompanySyncLog(
                    organization=organization,
                    installation=installation,
                    company=company,
                    actor=user,
                    action=ApolloCompanySyncLog.Action.IMPORT,
                    outcome=ApolloCompanySyncLog.Outcome.SUCCESS,
                    message='Empresa importada do Apollo para o CRM.',
                    remote_payload=remote_company.get('raw_payload', {}),
                )
            )
        ApolloCompanySyncLogRepository.bulk_create(sync_logs)
        return persisted_companies

    @staticmethod
    @transaction.atomic
    def sync_companies_to_hubspot(*, user, organization, companies):
        installation = ApolloInstallationService.get_installation(organization=organization)
        ApolloAuthorizationService.ensure_operator_access(user=user, organization=organization)
        synced_companies = HubSpotCompanyService.sync_companies(
            user=user,
            organization=organization,
            companies=companies,
        )
        ApolloCompanySyncLogRepository.bulk_create(
            [
                ApolloCompanySyncLog(
                    organization=organization,
                    installation=installation,
                    company=company,
                    actor=user,
                    action=ApolloCompanySyncLog.Action.SYNC_TO_HUBSPOT,
                    outcome=ApolloCompanySyncLog.Outcome.SUCCESS,
                    message='Empresa sincronizada com o HubSpot a partir do Apollo.',
                    remote_payload={},
                )
                for company in synced_companies
            ]
        )
        return synced_companies


class ApolloPersonService:
    @staticmethod
    def build_person_rows(*, organization):
        persons = [
            person
            for person in PersonRepository.list_for_organization(organization)
            if person.apollo_person_id
        ]
        return [
            {
                'person': person,
                'is_apollo_synced': bool(person.apollo_person_id),
            }
            for person in persons
        ]

    @staticmethod
    def build_enrichment_rows(*, organization):
        persons = [
            person
            for person in PersonRepository.list_for_organization(organization)
            if person.apollo_person_id
        ]
        rows = []
        for person in persons:
            has_uncensored_last_name = bool(person.last_name and '*' not in person.last_name)
            has_email = bool(person.email)
            rows.append(
                {
                    'person': person,
                    'has_email': has_email,
                    'has_phone': bool(person.phone),
                    'has_uncensored_last_name': has_uncensored_last_name,
                    'is_enriched': has_email and has_uncensored_last_name,
                    'is_phone_enriched': bool(person.phone),
                }
            )
        return rows

    @staticmethod
    def build_recent_enrichment_jobs(*, organization):
        jobs = list(ApolloPeopleEnrichmentJobRepository.list_recent_for_organization(organization, limit=10))
        rows = []
        for job in jobs:
            rows.append(
                {
                    'job': job,
                    'items': list(ApolloPeopleEnrichmentItemRepository.list_for_job(job)),
                }
            )
        return rows

    @staticmethod
    def resolve_public_base_url(*, request=None):
        configured_base_url = (getattr(settings, 'APP_BASE_URL', '') or '').strip().rstrip('/')
        if configured_base_url:
            return configured_base_url
        if request is None:
            return ''
        return request.build_absolute_uri('/').rstrip('/')

    @staticmethod
    def validate_phone_enrichment_target(*, request=None):
        base_url = ApolloPersonService.resolve_public_base_url(request=request)
        if not base_url:
            raise ValidationError(
                'Configure APP_BASE_URL com a URL publica HTTPS do CRM antes de pedir telefone via Apollo.'
            )
        parsed = urlparse(base_url)
        host = (parsed.hostname or '').lower()
        if parsed.scheme != 'https':
            raise ValidationError('O webhook do Apollo exige HTTPS. Ajuste APP_BASE_URL para usar https://.')
        if host in {'localhost', '127.0.0.1'} or host.endswith('.local'):
            raise ValidationError(
                'O webhook do Apollo nao consegue chamar localhost. Use producao ou um tunel publico HTTPS.'
            )
        return base_url

    @staticmethod
    def build_webhook_url(*, job, request=None):
        base_url = ApolloPersonService.validate_phone_enrichment_target(request=request)
        path = reverse('apollo_integration:people_enrichment_webhook', args=[job.public_id])
        return f'{base_url}{path}?token={job.webhook_token}'

    @staticmethod
    def refresh_enrichment_job(job):
        items = list(ApolloPeopleEnrichmentItemRepository.list_for_job(job))
        total_people = len(items)
        processed_people = len([item for item in items if item.status != ApolloPeopleEnrichmentItem.Status.WAITING_WEBHOOK])
        success_people = len([item for item in items if item.status == ApolloPeopleEnrichmentItem.Status.COMPLETED])
        failed_people = len([item for item in items if item.status == ApolloPeopleEnrichmentItem.Status.FAILED])

        if job.fetch_phone and any(item.status == ApolloPeopleEnrichmentItem.Status.WAITING_WEBHOOK for item in items):
            status = ApolloPeopleEnrichmentJob.Status.WEBHOOK_PENDING
            completed_at = None
        elif failed_people:
            status = ApolloPeopleEnrichmentJob.Status.COMPLETED_WITH_ERRORS
            completed_at = timezone.now()
        else:
            status = ApolloPeopleEnrichmentJob.Status.COMPLETED
            completed_at = timezone.now()

        job.total_people = total_people
        job.processed_people = processed_people
        job.success_people = success_people
        job.failed_people = failed_people
        job.status = status
        job.completed_at = completed_at
        job.save(
            update_fields=[
                'total_people',
                'processed_people',
                'success_people',
                'failed_people',
                'status',
                'completed_at',
                'updated_at',
            ]
        )
        return job

    @staticmethod
    def _apply_enriched_payload_to_person(*, person, remote_person, user=None, synced_at=None):
        changed = False
        first_name = (remote_person.get('first_name') or '').strip()
        last_name = (remote_person.get('last_name') or '').strip()
        email = (remote_person.get('email') or '').strip().lower()

        if first_name and person.first_name != first_name:
            person.first_name = first_name
            changed = True
        if last_name and person.last_name != last_name:
            person.last_name = last_name
            changed = True
        if email and person.email != email:
            person.email = email
            changed = True

        if changed:
            if user is not None:
                person.updated_by = user
            if synced_at is not None:
                person.updated_at = synced_at
            ApolloBulkPreparationService.prepare_person(person)
        return changed

    @staticmethod
    def _extract_phone_from_remote_person(remote_person):
        phone_candidates = [
            remote_person.get('phone'),
            remote_person.get('direct_phone'),
            remote_person.get('mobile_phone'),
        ]
        phone_numbers = remote_person.get('phone_numbers') or remote_person.get('phones') or []
        if isinstance(phone_numbers, list):
            for phone_payload in phone_numbers:
                if isinstance(phone_payload, dict):
                    phone_candidates.extend(
                        [
                            phone_payload.get('sanitized_number'),
                            phone_payload.get('raw_number'),
                            phone_payload.get('number'),
                        ]
                    )
                elif phone_payload:
                    phone_candidates.append(str(phone_payload))

        for value in phone_candidates:
            if not value:
                continue
            try:
                return format_phone_display(normalize_phone(value))
            except ValidationError:
                continue
        return ''

    @staticmethod
    def build_company_filter_choices(*, organization):
        labels = []
        for company in CompanyRepository.list_for_organization(organization):
            labels.append((str(company.public_id), company.name))
        return labels

    @staticmethod
    def build_search_payload(*, organization, filters):
        payload = {
            'page': filters.get('page') or 1,
            'per_page': filters.get('per_page') or 25,
        }

        company = None
        company_public_id = filters.get('company_public_id')
        if company_public_id:
            company = CompanyRepository.get_for_organization_and_public_id(organization, company_public_id)

        company_domain = ''
        if company and company.website:
            parsed = urlparse(company.website if '://' in company.website else f'https://{company.website}')
            company_domain = (parsed.netloc or parsed.path or '').lower()
            if company_domain.startswith('www.'):
                company_domain = company_domain[4:]

        if company_domain:
            payload['q_organization_domains_list'] = [company_domain]
        elif company and company.name:
            payload['q_organization_name'] = company.name
        elif filters.get('q_organization_domains'):
            payload['q_organization_domains_list'] = filters['q_organization_domains']
        elif filters.get('q_organization_name'):
            payload['q_organization_name'] = filters['q_organization_name']

        if filters.get('person_titles'):
            payload['person_titles'] = filters['person_titles']
        if filters.get('q_keywords'):
            payload['q_keywords'] = filters['q_keywords']
        if filters.get('contact_email_status'):
            payload['contact_email_status'] = filters['contact_email_status']
        return payload

    @staticmethod
    def list_remote_people(*, organization, filters):
        client = ApolloInstallationService.build_client(organization=organization)
        local_persons = list(PersonRepository.list_for_organization(organization))
        local_companies = list(CompanyRepository.list_for_organization(organization))
        person_indexes = build_person_indexes(persons=local_persons)
        company_indexes = build_company_indexes(companies=local_companies)
        payload = ApolloPersonService.build_search_payload(organization=organization, filters=filters)
        search_result = client.search_people(payload=payload)

        remote_people = []
        for remote_person in search_result['people']:
            linked_person = match_person(
                remote_contact=remote_person,
                person_indexes=person_indexes,
                integration_key='apollo',
            )
            linked_company = match_company(
                remote_company={
                    'apollo_company_id': remote_person.get('organization_apollo_company_id', ''),
                    'name': remote_person.get('organization_name', ''),
                    'website': remote_person.get('organization_website', ''),
                },
                company_indexes=company_indexes,
            )
            remote_people.append(
                {
                    **remote_person,
                    'linked_person': linked_person,
                    'linked_company': linked_company,
                    'is_saved_in_crm': linked_person is not None,
                }
            )

        return {
            'people': remote_people,
            'pagination': search_result.get('pagination') or {},
            'payload': payload,
        }

    @staticmethod
    @transaction.atomic
    def import_remote_people(*, user, organization, remote_people):
        ApolloAuthorizationService.ensure_operator_access(user=user, organization=organization)
        local_persons = list(PersonRepository.list_for_organization(organization))
        local_companies = list(CompanyRepository.list_for_organization(organization))
        person_indexes = build_person_indexes(persons=local_persons)
        company_indexes = build_company_indexes(companies=local_companies)
        synced_at = timezone.now()

        persons_to_create = []
        persons_to_update = []
        persisted_people = []

        for remote_person in remote_people:
            matched_person = match_person(
                remote_contact=remote_person,
                person_indexes=person_indexes,
                integration_key='apollo',
            )
            linked_company = match_company(
                remote_company={
                    'apollo_company_id': remote_person.get('organization_apollo_company_id', ''),
                    'name': remote_person.get('organization_name', ''),
                    'website': remote_person.get('organization_website', ''),
                },
                company_indexes=company_indexes,
            )
            first_name = (remote_person.get('first_name') or '').strip() or 'Sem nome'
            last_name = (
                remote_person.get('last_name')
                or remote_person.get('last_name_obfuscated')
                or ''
            ).strip()

            if matched_person is not None:
                changed = False
                if not matched_person.apollo_person_id and remote_person.get('apollo_person_id'):
                    matched_person.apollo_person_id = remote_person['apollo_person_id']
                    changed = True
                if not matched_person.company and linked_company is not None:
                    matched_person.company = linked_company
                    changed = True
                if changed:
                    matched_person.updated_by = user
                    matched_person.updated_at = synced_at
                    ApolloBulkPreparationService.prepare_person(matched_person)
                    persons_to_update.append(matched_person)
                persisted_people.append(matched_person)
                continue

            person = Person(
                organization=organization,
                apollo_person_id=remote_person.get('apollo_person_id', ''),
                company=linked_company,
                phone='',
                email='',
                first_name=first_name,
                last_name=last_name,
                created_by=user,
                updated_by=user,
            )
            ApolloBulkPreparationService.prepare_person(person)
            persons_to_create.append(person)
            local_persons.append(person)
            person_indexes = build_person_indexes(persons=local_persons)
            persisted_people.append(person)

        if persons_to_create:
            PersonRepository.bulk_create(persons_to_create)
        if persons_to_update:
            PersonRepository.bulk_update(
                persons_to_update,
                ['apollo_person_id', 'company', 'updated_by', 'updated_at'],
            )
        return persisted_people

    @staticmethod
    @transaction.atomic
    def enrich_people(*, user, organization, people, fetch_phone=False, request=None):
        ApolloAuthorizationService.ensure_operator_access(user=user, organization=organization)
        installation = ApolloInstallationService.get_installation(organization=organization)
        client = ApolloInstallationService.build_client(organization=organization)
        people_by_apollo_id = {
            person.apollo_person_id: person
            for person in people
            if person.apollo_person_id
        }
        apollo_person_ids = [apollo_person_id for apollo_person_id in people_by_apollo_id.keys() if apollo_person_id]
        if not apollo_person_ids:
            raise ValidationError('Selecione pelo menos uma pessoa sincronizada com o Apollo para enriquecer.')

        synced_at = timezone.now()
        enrichment_job = None
        webhook_url = ''
        if fetch_phone:
            ApolloPersonService.validate_phone_enrichment_target(request=request)
            enrichment_job = ApolloPeopleEnrichmentJobRepository.create(
                organization=organization,
                installation=installation,
                actor=user,
                status=ApolloPeopleEnrichmentJob.Status.WEBHOOK_PENDING,
                fetch_phone=True,
                webhook_token=secrets.token_urlsafe(32),
                total_people=len(apollo_person_ids),
                processed_people=0,
                success_people=0,
                failed_people=0,
                started_at=synced_at,
                request_payload={'apollo_person_ids': apollo_person_ids},
            )
            webhook_url = ApolloPersonService.build_webhook_url(job=enrichment_job, request=request)

        enriched_payload_by_apollo_id = {}
        enrichment_items = []
        for start_index in range(0, len(apollo_person_ids), APOLLO_BULK_ENRICH_MAX_BATCH_SIZE):
            batch_ids = apollo_person_ids[start_index:start_index + APOLLO_BULK_ENRICH_MAX_BATCH_SIZE]
            details = []
            for apollo_person_id in batch_ids:
                person = people_by_apollo_id[apollo_person_id]
                detail = {'id': apollo_person_id}
                if person.company and person.company.website:
                    detail['organization_website'] = person.company.website
                details.append(detail)

            result = client.enrich_people(
                details=details,
                reveal_personal_emails=True,
                reveal_phone_number=fetch_phone,
                webhook_url=webhook_url,
            )
            if enrichment_job is not None:
                for detail in details:
                    enrichment_items.append(
                        ApolloPeopleEnrichmentItem(
                            organization=organization,
                            job=enrichment_job,
                            person=people_by_apollo_id[detail['id']],
                            apollo_person_id=detail['id'],
                            status=ApolloPeopleEnrichmentItem.Status.WAITING_WEBHOOK,
                            requested_phone=True,
                            request_payload=detail,
                        )
                    )
            for remote_person in result['people']:
                remote_apollo_person_id = remote_person.get('apollo_person_id', '')
                if remote_apollo_person_id:
                    enriched_payload_by_apollo_id[remote_apollo_person_id] = remote_person

        persons_to_update = []
        enriched_count = 0
        for apollo_person_id, person in people_by_apollo_id.items():
            remote_person = enriched_payload_by_apollo_id.get(apollo_person_id)
            if remote_person is None:
                continue

            changed = ApolloPersonService._apply_enriched_payload_to_person(
                person=person,
                remote_person=remote_person,
                user=user,
                synced_at=synced_at,
            )

            if changed:
                persons_to_update.append(person)
                enriched_count += 1

        if persons_to_update:
            PersonRepository.bulk_update(
                persons_to_update,
                ['first_name', 'last_name', 'email', 'email_lookup', 'updated_by', 'updated_at'],
            )

        if enrichment_items:
            ApolloPeopleEnrichmentItemRepository.bulk_create(enrichment_items)
        if enrichment_job is not None:
            ApolloPersonService.refresh_enrichment_job(enrichment_job)

        return {
            'requested_count': len(apollo_person_ids),
            'enriched_count': enriched_count,
            'updated_people': persons_to_update,
            'enrichment_job': enrichment_job,
            'fetch_phone': fetch_phone,
        }

    @staticmethod
    @transaction.atomic
    def process_enrichment_webhook(*, job, payload):
        job.last_webhook_payload = payload
        job.save(update_fields=['last_webhook_payload', 'updated_at'])

        remote_people = []
        if isinstance(payload, dict):
            if isinstance(payload.get('people'), list):
                remote_people = [item for item in payload.get('people', []) if isinstance(item, dict)]
            elif isinstance(payload.get('matches'), list):
                remote_people = [item for item in payload.get('matches', []) if isinstance(item, dict)]
            elif isinstance(payload.get('person'), dict):
                remote_people = [payload.get('person')]

        synced_at = timezone.now()
        persons_to_update = []
        for remote_person in remote_people:
            apollo_person_id = str(remote_person.get('id') or remote_person.get('apollo_person_id') or '').strip()
            if not apollo_person_id:
                continue

            item = ApolloPeopleEnrichmentItemRepository.get_for_job_and_apollo_person_id(job, apollo_person_id)
            if item is None:
                continue

            item.response_payload = remote_person
            item.webhook_payload = payload
            item.webhook_received_at = synced_at

            person = item.person
            person_changed = ApolloPersonService._apply_enriched_payload_to_person(
                person=person,
                remote_person={
                    'first_name': remote_person.get('first_name'),
                    'last_name': remote_person.get('last_name'),
                    'email': ApolloClient._resolve_email(
                        remote_person.get('email'),
                        remote_person.get('work_email'),
                        remote_person.get('emails'),
                        remote_person.get('personal_emails'),
                    ),
                },
                synced_at=synced_at,
            )

            if item.requested_phone:
                phone_value = ApolloPersonService._extract_phone_from_remote_person(remote_person)
                if phone_value and person.phone != phone_value:
                    person.phone = phone_value
                    person.updated_at = synced_at
                    ApolloBulkPreparationService.prepare_person(person)
                    person_changed = True
                    item.phone_enriched = True

            if person_changed:
                persons_to_update.append(person)

            item.email_enriched = bool(person.email)
            item.status = ApolloPeopleEnrichmentItem.Status.COMPLETED
            item.error_message = ''
            item.save(
                update_fields=[
                    'response_payload',
                    'webhook_payload',
                    'webhook_received_at',
                    'email_enriched',
                    'phone_enriched',
                    'status',
                    'error_message',
                    'updated_at',
                ]
            )

        if persons_to_update:
            unique_people = []
            seen_ids = set()
            for person in persons_to_update:
                if person.pk in seen_ids:
                    continue
                seen_ids.add(person.pk)
                unique_people.append(person)
            PersonRepository.bulk_update(
                unique_people,
                ['first_name', 'last_name', 'email', 'email_lookup', 'phone', 'normalized_phone', 'updated_at'],
            )

        ApolloPersonService.refresh_enrichment_job(job)
        return job
