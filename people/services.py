from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from common.phone import normalize_phone
from people.repositories import PersonRepository


class PersonService:
    @staticmethod
    @transaction.atomic
    def create_person(*, user, organization, first_name, last_name, phone, bot_conversa_id=None):
        normalized_phone = normalize_phone(phone)
        bot_conversa_id = (bot_conversa_id or '').strip() or None

        if PersonRepository.get_for_organization_and_normalized_phone(organization, normalized_phone):
            raise ValidationError('Ja existe uma pessoa com este telefone na organizacao ativa.')
        if bot_conversa_id and PersonRepository.get_for_organization_and_bot_conversa_id(organization, bot_conversa_id):
            raise ValidationError('Ja existe uma pessoa com este ID do Bot Conversa na organizacao ativa.')

        try:
            return PersonRepository.create(
                organization=organization,
                bot_conversa_id=bot_conversa_id,
                phone=phone,
                first_name=first_name,
                last_name=last_name,
                created_by=user,
                updated_by=user,
            )
        except IntegrityError as exc:
            raise ValidationError('Ja existe uma pessoa com este telefone ou ID do Bot Conversa na organizacao ativa.') from exc

    @staticmethod
    @transaction.atomic
    def assign_bot_conversa_id(*, user, organization, person, bot_conversa_id):
        normalized_bot_conversa_id = (bot_conversa_id or '').strip() or None
        if normalized_bot_conversa_id is None:
            return person

        if person.organization_id != organization.id:
            raise ValidationError('A pessoa selecionada nao pertence a organizacao ativa.')

        existing_person = PersonRepository.get_for_organization_and_bot_conversa_id(
            organization,
            normalized_bot_conversa_id,
        )
        if existing_person and existing_person.pk != person.pk:
            raise ValidationError('Ja existe uma pessoa com este ID do Bot Conversa na organizacao ativa.')

        if person.bot_conversa_id == normalized_bot_conversa_id:
            return person

        person.bot_conversa_id = normalized_bot_conversa_id
        person.updated_by = user
        person.save(update_fields=['bot_conversa_id', 'updated_by', 'updated_at'])
        return person
