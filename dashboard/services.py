from organizations.models import OrganizationInvite, OrganizationMembership
from organizations.repositories import InviteRepository, MembershipRepository


class DashboardMetricsService:
    @staticmethod
    def build_summary(*, organization):
        if organization is None:
            return None

        return {
            'member_count': MembershipRepository.count_for_organization(organization),
            'manager_count': MembershipRepository.count_for_roles(
                organization,
                [
                    OrganizationMembership.Role.OWNER,
                    OrganizationMembership.Role.ADMIN,
                ],
            ),
            'available_invite_count': InviteRepository.count_by_status(
                organization,
                OrganizationInvite.Status.AVAILABLE,
            ),
            'used_invite_count': InviteRepository.count_by_status(
                organization,
                OrganizationInvite.Status.USED,
            ),
            'recent_invites': InviteRepository.list_recent_for_organization(organization, limit=5),
        }
