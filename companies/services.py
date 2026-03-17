from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from companies.repositories import CompanyRepository


class CompanyService:
    @staticmethod
    @transaction.atomic
    def create_company(*, user, organization, name, website='', phone='', hubspot_company_id=''):
        try:
            return CompanyRepository.create(
                organization=organization,
                hubspot_company_id=(hubspot_company_id or '').strip(),
                name=name,
                website=website,
                phone=phone,
                created_by=user,
                updated_by=user,
            )
        except IntegrityError as exc:
            raise ValidationError('Já existe uma empresa com este ID do HubSpot na organização ativa.') from exc

    @staticmethod
    @transaction.atomic
    def update_company(*, user, organization, company, name, website='', phone='', hubspot_company_id=''):
        if company.organization_id != organization.id:
            raise ValidationError('A empresa selecionada não pertence à organização ativa.')

        try:
            return CompanyRepository.update(
                company,
                hubspot_company_id=(hubspot_company_id or '').strip(),
                name=name,
                website=website,
                phone=phone,
                updated_by=user,
            )
        except IntegrityError as exc:
            raise ValidationError('Já existe uma empresa com este ID do HubSpot na organização ativa.') from exc
