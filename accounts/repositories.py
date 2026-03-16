from accounts.models import User
from common.encryption import build_email_lookup, normalize_email_address


class UserRepository:
    @staticmethod
    def create_user(*, full_name, email, password):
        return User.objects.create_user(
            full_name=full_name,
            email=email,
            username=email,
            password=password,
        )

    @staticmethod
    def get_by_email(email):
        normalized_email = normalize_email_address(email)
        return User.objects.filter(email_lookup=build_email_lookup(normalized_email)).first()
