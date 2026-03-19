from django.core.exceptions import ValidationError


def normalize_cnpj(value):
    digits = ''.join(character for character in str(value or '').strip() if character.isdigit())
    if not digits:
        return ''
    if len(digits) != 14:
        raise ValidationError('Informe um CNPJ valido com 14 digitos, sem mascara.')
    return digits
