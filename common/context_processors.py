from admin_panel.services import AdminAuthorizationService
from integrations.services import InstalledAppNavigationService


def active_organization(request):
    active_organization = getattr(request, 'active_organization', None)

    return {
        'active_organization': active_organization,
        'active_membership': getattr(request, 'active_membership', None),
        'sidebar_installed_apps': InstalledAppNavigationService.build_navigation_items(
            organization=active_organization,
        ),
        'has_admin_panel_access': AdminAuthorizationService.has_panel_access(getattr(request, 'user', None)),
    }
