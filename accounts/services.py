from datetime import timedelta

from django.conf import settings
from django.contrib.auth import login
from django.utils import timezone

from admin_panel.services import AdminAccessAuditService
from accounts.repositories import UserRepository


class AccountService:
    FIXED_SESSION_DEADLINE_KEY = 'fixed_session_deadline'

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
        if remember_me:
            request.session.pop(AccountService.FIXED_SESSION_DEADLINE_KEY, None)
            request.session.set_expiry(settings.SESSION_COOKIE_AGE)
        else:
            request.session[AccountService.FIXED_SESSION_DEADLINE_KEY] = (
                timezone.now() + timedelta(seconds=settings.NON_REMEMBERED_SESSION_AGE)
            ).isoformat()
            request.session.set_expiry(settings.NON_REMEMBERED_SESSION_AGE)
        AdminAccessAuditService.record_login(request=request, user=user)

    @staticmethod
    def has_fixed_session_expired(request):
        deadline_value = request.session.get(AccountService.FIXED_SESSION_DEADLINE_KEY)
        if not deadline_value:
            return False

        try:
            deadline = timezone.datetime.fromisoformat(deadline_value)
        except ValueError:
            request.session.pop(AccountService.FIXED_SESSION_DEADLINE_KEY, None)
            return False

        if timezone.is_naive(deadline):
            deadline = timezone.make_aware(deadline, timezone.get_current_timezone())

        return timezone.now() >= deadline
