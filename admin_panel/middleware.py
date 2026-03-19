from admin_panel.services import AdminAccessAuditService


class AdminAccessAuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            AdminAccessAuditService.sync_authenticated_session(request=request)

        return self.get_response(request)

