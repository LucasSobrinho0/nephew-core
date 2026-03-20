from django.contrib.auth import logout
from django.shortcuts import redirect

from accounts.services import AccountService
from admin_panel.services import AdminAccessAuditService
from organizations.services import ActiveOrganizationService


class SessionTimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and AccountService.has_fixed_session_expired(request):
            AdminAccessAuditService.record_logout(request=request)
            logout(request)
            return redirect('accounts:login')

        return self.get_response(request)


class ActiveOrganizationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.active_organization = None
        request.active_membership = None

        if request.user.is_authenticated:
            ActiveOrganizationService.synchronize_request(request)

        return self.get_response(request)
