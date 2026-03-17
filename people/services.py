from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from common.encryption import build_email_lookup, normalize_email_address
from common.phone import normalize_phone
from people.repositories import PersonRepository


class PersonService:
    @staticmethod
    @transaction.atomic
    def create_person(*, user, organization, first_name, last_name, phone, email='', bot_conversa_id=None):
        normalized_phone = normalize_phone(phone)
        normalized_email = normalize_email_address(email) if email else ''
        email_lookup = build_email_lookup(normalized_email) if normalized_email else ''
        bot_conversa_id = (bot_conversa_id or '').strip() or None

        if PersonRepository.get_for_organization_and_normalized_phone(organization, normalized_phone):
            raise ValidationError('Já existe uma pessoa com este telefone na organização ativa.')
        if email_lookup and PersonRepository.get_for_organization_and_email_lookup(organization, email_lookup):
            raise ValidationError('Já existe uma pessoa com este e-mail na organização ativa.')
        if bot_conversa_id and PersonRepository.get_for_organization_and_bot_conversa_id(organization, bot_conversa_id):
            raise ValidationError('Já existe uma pessoa com este ID do Bot Conversa na organização ativa.')

        try:
            return PersonRepository.create(
                organization=organization,
                bot_conversa_id=bot_conversa_id,
                phone=phone,
                email=normalized_email,
                first_name=first_name,
                last_name=last_name,
                created_by=user,
                updated_by=user,
            )
        except IntegrityError as exc:
            raise ValidationError('Já existe uma pessoa com este telefone, e-mail ou ID do Bot Conversa na organização ativa.') from exc

    @staticmethod
    @transaction.atomic
    def update_person(*, user, organization, person, first_name, last_name, phone, email=''):
        if person.organization_id != organization.id:
            raise ValidationError('A pessoa selecionada não pertence à organização ativa.')

        normalized_phone = normalize_phone(phone)
        normalized_email = normalize_email_address(email) if email else ''
        email_lookup = build_email_lookup(normalized_email) if normalized_email else ''

        existing_phone_person = PersonRepository.get_for_organization_and_normalized_phone(organization, normalized_phone)
        if existing_phone_person and existing_phone_person.pk != person.pk:
            raise ValidationError('Já existe uma pessoa com este telefone na organização ativa.')

        existing_email_person = None
        if email_lookup:
            existing_email_person = PersonRepository.get_for_organization_and_email_lookup(organization, email_lookup)
        if existing_email_person and existing_email_person.pk != person.pk:
            raise ValidationError('Já existe uma pessoa com este e-mail na organização ativa.')

        try:
            return PersonRepository.update(
                person,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                email=normalized_email,
                updated_by=user,
            )
        except IntegrityError as exc:
            raise ValidationError('Já existe uma pessoa com este telefone ou e-mail na organização ativa.') from exc

    @staticmethod
    @transaction.atomic
    def assign_bot_conversa_id(*, user, organization, person, bot_conversa_id):
        normalized_bot_conversa_id = (bot_conversa_id or '').strip() or None
        if normalized_bot_conversa_id is None:
            return person

        if person.organization_id != organization.id:
            raise ValidationError('A pessoa selecionada não pertence à organização ativa.')

        existing_person = PersonRepository.get_for_organization_and_bot_conversa_id(
            organization,
            normalized_bot_conversa_id,
        )
        if existing_person and existing_person.pk != person.pk:
            raise ValidationError('Já existe uma pessoa com este ID do Bot Conversa na organização ativa.')

        if person.bot_conversa_id == normalized_bot_conversa_id:
            return person

        person.bot_conversa_id = normalized_bot_conversa_id
        person.updated_by = user
        person.save(update_fields=['bot_conversa_id', 'updated_by', 'updated_at'])
        return person
