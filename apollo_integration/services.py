from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apollo_integration.client import ApolloClient
from apollo_integration.constants import APOLLO_APP_CODE
from apollo_integration.exceptions import ApolloApiError, ApolloConfigurationError
from apollo_integration.models import ApolloCompanySyncLog
from apollo_integration.repositories import ApolloCompanySyncLogRepository, ApolloUsageSnapshotRepository
from common.matching import build_company_indexes, match_company
from common.phone import format_phone_display, normalize_phone
from companies.models import Company
from companies.repositories import CompanyRepository
from hubspot_integration.services import HubSpotCompanyService
from integrations.repositories import AppCatalogRepository, AppCredentialRepository, AppInstallationRepository
from organizations.repositories import MembershipRepository


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
            message = 'Empresa importada do Apollo para o CRM.'
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
                message = 'Empresa do Apollo vinculada ao CRM existente.'
                sync_logs.append(
                    ApolloCompanySyncLog(
                        organization=organization,
                        installation=installation,
                        company=matched_company,
                        actor=user,
                        action=ApolloCompanySyncLog.Action.IMPORT,
                        outcome=ApolloCompanySyncLog.Outcome.SUCCESS,
                        message=message,
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
