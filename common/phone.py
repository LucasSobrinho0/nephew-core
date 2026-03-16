from django.core.exceptions import ValidationError


def normalize_phone(value):
    raw_value = (value or '').strip()
    digits = ''.join(character for character in raw_value if character.isdigit())

    if digits.startswith('00'):
        digits = digits[2:]

    if len(digits) in {10, 11}:
        digits = f'55{digits}'

    if len(digits) not in {12, 13}:
        raise ValidationError('Informe um telefone valido com DDD.')

    return digits


def format_phone_display(normalized_phone):
    digits = ''.join(character for character in (normalized_phone or '') if character.isdigit())
    if not digits:
        return ''

    if digits.startswith('55') and len(digits) in {12, 13}:
        country_code = digits[:2]
        area_code = digits[2:4]
        local_number = digits[4:]

        if len(local_number) == 9:
            return f'+{country_code} {area_code} {local_number[:5]}-{local_number[5:]}'
        if len(local_number) == 8:
            return f'+{country_code} {area_code} {local_number[:4]}-{local_number[4:]}'

    return f'+{digits}'


def build_e164_phone(normalized_phone):
    digits = ''.join(character for character in (normalized_phone or '') if character.isdigit())
    return f'+{digits}' if digits else ''
