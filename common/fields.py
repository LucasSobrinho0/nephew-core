from django.db import models

from common.encryption import DEFAULT_ENCRYPTION_PURPOSE, decrypt_text, encrypt_text


class EncryptedTextField(models.TextField):
    description = 'Encrypted text value stored at rest'

    def __init__(self, *args, purpose=DEFAULT_ENCRYPTION_PURPOSE, fallback_purposes=(), **kwargs):
        self.purpose = purpose
        self.fallback_purposes = tuple(fallback_purposes)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self.purpose != DEFAULT_ENCRYPTION_PURPOSE:
            kwargs['purpose'] = self.purpose
        if self.fallback_purposes:
            kwargs['fallback_purposes'] = self.fallback_purposes
        return name, path, args, kwargs

    def from_db_value(self, value, expression, connection):
        return decrypt_text(
            value,
            purpose=self.purpose,
            fallback_purposes=self.fallback_purposes,
        )

    def to_python(self, value):
        if value is None or not isinstance(value, str):
            return value
        return decrypt_text(
            value,
            purpose=self.purpose,
            fallback_purposes=self.fallback_purposes,
        )

    def get_prep_value(self, value):
        if value is None:
            return value
        return encrypt_text(value, purpose=self.purpose)
