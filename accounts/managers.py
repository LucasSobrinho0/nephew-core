from django.contrib.auth.base_user import BaseUserManager

from common.encryption import build_email_lookup, normalize_email_address


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('The email address must be provided.')

        email = normalize_email_address(self.normalize_email(email))
        email_lookup = build_email_lookup(email)
        username = extra_fields.pop('username', '') or email_lookup

        user = self.model(email=email, username=username, email_lookup=email_lookup, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def get_by_natural_key(self, email):
        normalized_email = normalize_email_address(self.normalize_email(email))
        return self.get(email_lookup=build_email_lookup(normalized_email))

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(email, password, **extra_fields)
