from people.models import Person


class PersonRepository:
    @staticmethod
    def list_for_organization(organization):
        return (
            Person.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .order_by('first_name', 'last_name', 'normalized_phone')
        )

    @staticmethod
    def count_for_organization(organization):
        return PersonRepository.list_for_organization(organization).count()

    @staticmethod
    def get_for_organization_and_public_id(organization, public_id):
        return (
            Person.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .filter(public_id=public_id)
            .first()
        )

    @staticmethod
    def get_for_organization_and_normalized_phone(organization, normalized_phone):
        return (
            Person.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .filter(normalized_phone=normalized_phone)
            .first()
        )

    @staticmethod
    def get_for_organization_and_email_lookup(organization, email_lookup):
        return (
            Person.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .filter(email_lookup=email_lookup)
            .first()
        )

    @staticmethod
    def get_for_organization_and_bot_conversa_id(organization, bot_conversa_id):
        return (
            Person.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .filter(bot_conversa_id=bot_conversa_id)
            .first()
        )

    @staticmethod
    def get_for_organization_and_hubspot_contact_id(organization, hubspot_contact_id):
        return (
            Person.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .filter(hubspot_contact_id=hubspot_contact_id)
            .first()
        )

    @staticmethod
    def list_for_organization_and_public_ids(organization, public_ids):
        return (
            Person.objects.active()
            .for_organization(organization)
            .with_related_objects()
            .filter(public_id__in=public_ids)
            .order_by('first_name', 'last_name')
        )

    @staticmethod
    def update(person, **kwargs):
        for field_name, field_value in kwargs.items():
            setattr(person, field_name, field_value)
        person.save()
        return person

    @staticmethod
    def create(**kwargs):
        return Person.objects.create(**kwargs)
