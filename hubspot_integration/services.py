from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from companies.repositories import CompanyRepository
from companies.services import CompanyService
from hubspot_integration.client import HubSpotClient
from hubspot_integration.constants import HUBSPOT_APP_CODE
from hubspot_integration.exceptions import HubSpotConfigurationError
from hubspot_integration.models import HubSpotDeal, HubSpotPipelineCache, HubSpotSyncLog
from hubspot_integration.repositories import HubSpotDealRepository, HubSpotPipelineRepository, HubSpotSyncLogRepository
from integrations.repositories import AppCatalogRepository, AppCredentialRepository, AppInstallationRepository
from organizations.repositories import MembershipRepository
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


class HubSpotDashboardService:
    @staticmethod
    def build_summary(*, organization):
        installation = HubSpotInstallationService.get_installation(organization=organization)
        return {
            'installation': installation,
            'company_count': CompanyRepository.list_for_organization(organization).count(),
            'synced_company_count': CompanyRepository.list_for_organization(organization).exclude(hubspot_company_id='').count(),
            'synced_person_count': PersonRepository.list_for_organization(organization).exclude(hubspot_contact_id='').count(),
            'pipeline_count': HubSpotPipelineRepository.list_for_organization(organization).count(),
            'deal_count': HubSpotDealRepository.list_for_organization(organization).count(),
            'recent_sync_logs': HubSpotSyncLogRepository.list_recent_for_organization(organization, limit=5),
            'recent_deals': HubSpotDealRepository.list_recent_for_organization(organization, limit=5),
        }


class HubSpotCompanyService:
    @staticmethod
    def build_company_rows(*, organization):
        companies = list(CompanyRepository.list_for_organization(organization))
        return [
            {
                'company': company,
                'is_synced': bool(company.hubspot_company_id),
            }
            for company in companies
        ]

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
    def sync_company(*, user, organization, company):
        installation = HubSpotInstallationService.get_installation(organization=organization)
        HubSpotAuthorizationService.ensure_operator_access(user=user, organization=organization)
        if company.organization_id != organization.id:
            raise ValidationError('A empresa selecionada não pertence à organização ativa.')

        client = HubSpotInstallationService.build_client(organization=organization)
        remote_company = client.create_or_get_company(
            name=company.name,
            website=company.website,
            phone=company.phone,
        )
        company.hubspot_company_id = remote_company['hubspot_company_id']
        company.updated_by = user
        company.save(update_fields=['hubspot_company_id', 'updated_by', 'updated_at'])

        HubSpotSyncLogRepository.create(
            organization=organization,
            installation=installation,
            company=company,
            actor=user,
            entity_type=HubSpotSyncLog.EntityType.COMPANY,
            outcome=HubSpotSyncLog.Outcome.SUCCESS,
            message='Empresa sincronizada com o HubSpot.',
            remote_payload=remote_company['raw_payload'],
        )
        return company

    @staticmethod
    @transaction.atomic
    def import_remote_company(*, user, organization, hubspot_company_id, name, website='', phone=''):
        HubSpotAuthorizationService.ensure_operator_access(user=user, organization=organization)
        existing_company = CompanyRepository.get_for_organization_and_hubspot_company_id(
            organization,
            hubspot_company_id,
        )
        if existing_company:
            return existing_company, False

        company = CompanyService.create_company(
            user=user,
            organization=organization,
            hubspot_company_id=hubspot_company_id,
            name=name,
            website=website,
            phone=phone,
        )
        return company, True

    @staticmethod
    def list_remote_companies(*, organization):
        client = HubSpotInstallationService.build_client(organization=organization)
        local_by_hubspot_id = {
            company.hubspot_company_id: company
            for company in CompanyRepository.list_for_organization(organization)
            if company.hubspot_company_id
        }
        remote_companies = []
        for remote_company in client.list_companies():
            remote_companies.append(
                {
                    **remote_company,
                    'linked_company': local_by_hubspot_id.get(remote_company['hubspot_company_id']),
                }
            )
        return remote_companies


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
        return [
            {
                'person': person,
                'is_synced': bool(person.hubspot_contact_id),
            }
            for person in persons
        ]

    @staticmethod
    @transaction.atomic
    def sync_person(*, user, organization, person):
        installation = HubSpotInstallationService.get_installation(organization=organization)
        HubSpotAuthorizationService.ensure_operator_access(user=user, organization=organization)
        if person.organization_id != organization.id:
            raise ValidationError('A pessoa selecionada não pertence à organização ativa.')

        client = HubSpotInstallationService.build_client(organization=organization)
        company_id = ''
        if person.company and person.company.hubspot_company_id:
            company_id = person.company.hubspot_company_id

        remote_contact = client.create_or_get_contact(
            first_name=person.first_name,
            last_name=person.last_name,
            email=person.email,
            phone=person.phone,
            company_id=company_id,
        )
        person.hubspot_contact_id = remote_contact['hubspot_contact_id']
        person.updated_by = user
        person.save(update_fields=['hubspot_contact_id', 'updated_by', 'updated_at'])

        HubSpotSyncLogRepository.create(
            organization=organization,
            installation=installation,
            person=person,
            actor=user,
            entity_type=HubSpotSyncLog.EntityType.PERSON,
            outcome=HubSpotSyncLog.Outcome.SUCCESS,
            message='Pessoa sincronizada com o HubSpot.',
            remote_payload=remote_contact['raw_payload'],
        )
        return person

    @staticmethod
    @transaction.atomic
    def import_remote_contact(
        *,
        user,
        organization,
        hubspot_contact_id,
        first_name='',
        last_name='',
        email='',
        phone='',
        company_name='',
        company_hubspot_id='',
    ):
        HubSpotAuthorizationService.ensure_operator_access(user=user, organization=organization)
        existing_person = PersonRepository.get_for_organization_and_hubspot_contact_id(organization, hubspot_contact_id)
        if existing_person:
            return existing_person, False

        company = None
        if company_hubspot_id:
            company = CompanyRepository.get_for_organization_and_hubspot_company_id(organization, company_hubspot_id)
        if company is None and company_name:
            company = CompanyService.create_company(
                user=user,
                organization=organization,
                name=company_name,
                hubspot_company_id=company_hubspot_id,
            )

        person = PersonService.create_person(
            user=user,
            organization=organization,
            first_name=first_name or 'Contato',
            last_name=last_name or 'HubSpot',
            email=email,
            phone=phone or HubSpotContactService.build_fallback_phone(hubspot_contact_id=hubspot_contact_id),
            hubspot_contact_id=hubspot_contact_id,
            company=company,
        )
        return person, True

    @staticmethod
    def list_remote_contacts(*, organization):
        client = HubSpotInstallationService.build_client(organization=organization)
        local_by_hubspot_id = {
            person.hubspot_contact_id: person
            for person in PersonRepository.list_for_organization(organization)
            if person.hubspot_contact_id
        }
        remote_contacts = []
        for remote_contact in client.list_contacts():
            remote_contacts.append(
                {
                    **remote_contact,
                    'linked_person': local_by_hubspot_id.get(remote_contact['hubspot_contact_id']),
                }
            )
        return remote_contacts


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

        client = HubSpotInstallationService.build_client(organization=organization)
        contact_ids = [
            person.hubspot_contact_id
            for person in PersonRepository.list_for_organization(organization).filter(company=company)
            if person.hubspot_contact_id
        ]
        stage_id = ''
        pipeline_stages = (pipeline.raw_payload or {}).get('stages') or []
        if pipeline_stages:
            stage_id = str(pipeline_stages[0].get('id') or '')

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
