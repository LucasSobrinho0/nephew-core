from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from companies.repositories import CompanyRepository


class CompanyService:
    @staticmethod
    @transaction.atomic
    def create_company(
        *,
        user,
        organization,
        name,
        cnpj='',
        website='',
        email='',
        phone='',
        segment='',
        employee_count=None,
        apollo_company_id='',
        hubspot_company_id='',
    ):
        try:
            return CompanyRepository.create(
                organization=organization,
                apollo_company_id=(apollo_company_id or '').strip(),
                hubspot_company_id=(hubspot_company_id or '').strip(),
                name=name,
                cnpj=(cnpj or '').strip(),
                website=website,
                email=email,
                phone=phone,
                segment=segment,
                employee_count=employee_count,
                created_by=user,
                updated_by=user,
            )
        except IntegrityError as exc:
            raise ValidationError('Ja existe uma empresa com este identificador externo ou CNPJ na organizacao ativa.') from exc

    @staticmethod
    @transaction.atomic
    def update_company(
        *,
        user,
        organization,
        company,
        name,
        cnpj='',
        website='',
        email='',
        phone='',
        segment='',
        employee_count=None,
        apollo_company_id='',
        hubspot_company_id='',
    ):
        if company.organization_id != organization.id:
            raise ValidationError('A empresa selecionada nao pertence a organizacao ativa.')

        try:
            return CompanyRepository.update(
                company,
                apollo_company_id=(apollo_company_id or '').strip(),
                hubspot_company_id=(hubspot_company_id or '').strip(),
                name=name,
                cnpj=(cnpj or '').strip(),
                website=website,
                email=email,
                phone=phone,
                segment=segment,
                employee_count=employee_count,
                updated_by=user,
            )
        except IntegrityError as exc:
            raise ValidationError('Ja existe uma empresa com este identificador externo ou CNPJ na organizacao ativa.') from exc
