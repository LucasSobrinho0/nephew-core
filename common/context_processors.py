from integrations.services import InstalledAppNavigationService


def active_organization(request):
    active_organization = getattr(request, 'active_organization', None)

    return {
        'active_organization': active_organization,
        'active_membership': getattr(request, 'active_membership', None),
        'sidebar_installed_apps': InstalledAppNavigationService.build_navigation_items(
            organization=active_organization,
        ),
    }
