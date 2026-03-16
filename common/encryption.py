import base64
import hashlib
import hmac
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

ENCRYPTED_VALUE_PREFIX = 'enc$'
DEFAULT_ENCRYPTION_PURPOSE = 'default'
APP_CREDENTIAL_ENCRYPTION_PURPOSE = 'app-credential'


def normalize_email_address(email):
    return email.strip().lower()


def _build_fernet_key(source_value, *, purpose):
    raw_value = f'{purpose}:{source_value}'.encode()
    return base64.urlsafe_b64encode(hashlib.sha256(raw_value).digest())


def get_encryption_source_value(*, purpose):
    if purpose == APP_CREDENTIAL_ENCRYPTION_PURPOSE:
        return (
            getattr(settings, 'APP_CREDENTIAL_ENCRYPTION_KEY', None)
            or getattr(settings, 'FIELD_ENCRYPTION_KEY', None)
            or settings.SECRET_KEY
        )

    return getattr(settings, 'FIELD_ENCRYPTION_KEY', None) or settings.SECRET_KEY


@lru_cache(maxsize=None)
def get_fernet(*, purpose=DEFAULT_ENCRYPTION_PURPOSE):
    configured_key = get_encryption_source_value(purpose=purpose)
    derivation_purpose = 'field-encryption'
    if purpose != DEFAULT_ENCRYPTION_PURPOSE:
        derivation_purpose = f'field-encryption:{purpose}'
    derived_key = _build_fernet_key(configured_key, purpose=derivation_purpose)
    return Fernet(derived_key)


def is_encrypted_value(value):
    return isinstance(value, str) and value.startswith(ENCRYPTED_VALUE_PREFIX)


def encrypt_text(value, *, purpose=DEFAULT_ENCRYPTION_PURPOSE):
    if value in (None, ''):
        return value

    if is_encrypted_value(value):
        return value

    token = get_fernet(purpose=purpose).encrypt(str(value).encode()).decode()
    return f'{ENCRYPTED_VALUE_PREFIX}{token}'


def decrypt_text(value, *, purpose=DEFAULT_ENCRYPTION_PURPOSE, fallback_purposes=()):
    if value in (None, ''):
        return value

    if not is_encrypted_value(value):
        return value

    token = value[len(ENCRYPTED_VALUE_PREFIX):]

    purposes = (purpose, *fallback_purposes)

    for configured_purpose in purposes:
        try:
            return get_fernet(purpose=configured_purpose).decrypt(token.encode()).decode()
        except InvalidToken:
            continue

    raise ValueError('Unable to decrypt the stored field value.')


def build_email_lookup(email):
    normalized_email = normalize_email_address(email)
    lookup_key = (getattr(settings, 'EMAIL_LOOKUP_KEY', None) or settings.SECRET_KEY).encode()
    digest = hmac.new(lookup_key, normalized_email.encode(), hashlib.sha256).hexdigest()
    return digest
