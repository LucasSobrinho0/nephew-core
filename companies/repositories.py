from companies.models import Company


class CompanyRepository:
    @staticmethod
    def list_for_organization(organization):
        return (
            Company.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .order_by('name', 'website')
        )

    @staticmethod
    def get_for_organization_and_public_id(organization, public_id):
        return (
            Company.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .filter(public_id=public_id)
            .first()
        )

    @staticmethod
    def get_for_organization_and_apollo_company_id(organization, apollo_company_id):
        return (
            Company.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .filter(apollo_company_id=apollo_company_id)
            .first()
        )

    @staticmethod
    def get_for_organization_and_hubspot_company_id(organization, hubspot_company_id):
        return (
            Company.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .filter(hubspot_company_id=hubspot_company_id)
            .first()
        )

    @staticmethod
    def get_for_organization_and_cnpj(organization, cnpj):
        return (
            Company.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .filter(cnpj=cnpj)
            .first()
        )

    @staticmethod
    def get_for_organization_and_name(organization, name):
        normalized_name = (name or '').strip()
        if not normalized_name:
            return None

        return (
            Company.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .filter(name__iexact=normalized_name)
            .first()
        )

    @staticmethod
    def list_for_organization_and_public_ids(organization, public_ids):
        return (
            Company.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .filter(public_id__in=public_ids)
            .order_by('name')
        )

    @staticmethod
    def list_for_organization_and_apollo_company_ids(organization, apollo_company_ids):
        return (
            Company.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .filter(apollo_company_id__in=apollo_company_ids)
        )

    @staticmethod
    def list_for_organization_and_hubspot_company_ids(organization, hubspot_company_ids):
        return (
            Company.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .filter(hubspot_company_id__in=hubspot_company_ids)
        )

    @staticmethod
    def create(**kwargs):
        return Company.objects.create(**kwargs)

    @staticmethod
    def update(company, **kwargs):
        for field_name, field_value in kwargs.items():
            setattr(company, field_name, field_value)
        company.save()
        return company

    @staticmethod
    def bulk_create(companies, **kwargs):
        return Company.objects.bulk_create(companies, **kwargs)

    @staticmethod
    def bulk_update(companies, fields, **kwargs):
        if not companies:
            return 0
        return Company.objects.bulk_update(companies, fields, **kwargs)
