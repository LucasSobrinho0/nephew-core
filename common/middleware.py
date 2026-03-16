from organizations.services import ActiveOrganizationService


class ActiveOrganizationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.active_organization = None
        request.active_membership = None

        if request.user.is_authenticated:
            ActiveOrganizationService.synchronize_request(request)

        return self.get_response(request)
