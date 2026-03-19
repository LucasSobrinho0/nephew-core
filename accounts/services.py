from django.contrib.auth import login

from admin_panel.services import AdminAccessAuditService
from accounts.repositories import UserRepository


class AccountService:
    @staticmethod
    def register_user(*, full_name, email, password):
        return UserRepository.create_user(
            full_name=full_name,
            email=email,
            password=password,
        )

    @staticmethod
    def login_user(request, user, remember_me):
        login(request, user)
        if not remember_me:
            request.session.set_expiry(0)
        AdminAccessAuditService.record_login(request=request, user=user)
