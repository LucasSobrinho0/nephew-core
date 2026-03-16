from django.contrib.auth.models import AbstractUser
from django.db import models

from accounts.managers import UserManager
from common.encryption import build_email_lookup, normalize_email_address
from common.fields import EncryptedTextField


class User(AbstractUser):
    full_name = models.CharField(max_length=255)
    email = EncryptedTextField(unique=True)
    email_lookup = models.CharField(max_length=64, unique=True, editable=False)
    username = models.CharField(max_length=150, unique=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    class Meta:
        ordering = ('full_name', 'email_lookup')

    def save(self, *args, **kwargs):
        if self.email:
            normalized_email = normalize_email_address(self.email)
            self.email = normalized_email
            self.email_lookup = build_email_lookup(normalized_email)
            self.username = self.email_lookup
        super().save(*args, **kwargs)

    def __str__(self):
        return self.full_name or self.email

    @property
    def initials(self):
        name_parts = [part for part in self.full_name.split(' ') if part]
        if len(name_parts) >= 2:
            return f'{name_parts[0][0]}{name_parts[-1][0]}'.upper()
        if name_parts:
            return name_parts[0][:2].upper()
        return self.email[:2].upper()
