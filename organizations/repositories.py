from organizations.models import Organization, OrganizationInvite, OrganizationMembership


class OrganizationRepository:
    @staticmethod
    def create(**kwargs):
        return Organization.objects.create(**kwargs)

    @staticmethod
    def get_by_public_id(public_id):
        return Organization.objects.filter(public_id=public_id, is_active=True).first()


class MembershipRepository:
    @staticmethod
    def list_for_user(user):
        return (
            OrganizationMembership.objects.select_related('organization', 'user')
            .filter(user=user, is_active=True, organization__is_active=True)
            .order_by('organization__name')
        )

    @staticmethod
    def list_for_organization(organization):
        return (
            OrganizationMembership.objects.select_related('user', 'organization')
            .filter(organization=organization, is_active=True, organization__is_active=True)
            .order_by('role', 'user__full_name', 'user__email')
        )

    @staticmethod
    def get_first_for_user(user):
        return MembershipRepository.list_for_user(user).first()

    @staticmethod
    def get_for_user_and_organization(user, organization):
        return MembershipRepository.list_for_user(user).filter(organization=organization).first()

    @staticmethod
    def get_for_user_and_organization_id(user, organization_id):
        return MembershipRepository.list_for_user(user).filter(organization_id=organization_id).first()

    @staticmethod
    def get_for_user_and_org_public_id(user, organization_public_id):
        return MembershipRepository.list_for_user(user).filter(organization__public_id=organization_public_id).first()

    @staticmethod
    def create(**kwargs):
        return OrganizationMembership.objects.create(**kwargs)

    @staticmethod
    def count_for_organization(organization):
        return MembershipRepository.list_for_organization(organization).count()

    @staticmethod
    def count_for_roles(organization, roles):
        return MembershipRepository.list_for_organization(organization).filter(role__in=roles).count()


class InviteRepository:
    @staticmethod
    def create(**kwargs):
        return OrganizationInvite.objects.create(**kwargs)

    @staticmethod
    def list_for_organization(organization):
        return (
            OrganizationInvite.objects.select_related('created_by', 'used_by', 'organization')
            .filter(organization=organization)
            .order_by('-created_at')
        )

    @staticmethod
    def list_recent_for_organization(organization, limit=5):
        return InviteRepository.list_for_organization(organization)[:limit]

    @staticmethod
    def get_by_code(code):
        return (
            OrganizationInvite.objects.select_related('organization', 'created_by', 'used_by')
            .filter(code=code)
            .first()
        )

    @staticmethod
    def count_by_status(organization, status):
        return InviteRepository.list_for_organization(organization).filter(status=status).count()

    @staticmethod
    def expire_outdated_for_organization(organization, threshold):
        return (
            OrganizationInvite.objects.filter(
                organization=organization,
                status=OrganizationInvite.Status.AVAILABLE,
                expires_at__isnull=False,
                expires_at__lte=threshold,
            ).update(status=OrganizationInvite.Status.EXPIRED)
        )
