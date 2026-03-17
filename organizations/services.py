import random
import re
import string

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from common.constants import ACTIVE_ORGANIZATION_SESSION_KEY
from organizations.models import Organization, OrganizationInvite, OrganizationMembership
from organizations.repositories import InviteRepository, MembershipRepository, OrganizationRepository


class ActiveOrganizationService:
    @staticmethod
    def set_active_organization(request, organization):
        request.session[ACTIVE_ORGANIZATION_SESSION_KEY] = organization.id
        request.active_organization = organization
        request.active_membership = MembershipRepository.get_for_user_and_organization(request.user, organization)

    @staticmethod
    def clear_active_organization(request):
        request.session.pop(ACTIVE_ORGANIZATION_SESSION_KEY, None)
        request.active_organization = None
        request.active_membership = None

    @staticmethod
    def synchronize_request(request):
        organization_id = request.session.get(ACTIVE_ORGANIZATION_SESSION_KEY)
        membership = None

        if organization_id:
            membership = MembershipRepository.get_for_user_and_organization_id(request.user, organization_id)

        if membership is None:
            membership = MembershipRepository.get_first_for_user(request.user)
            if membership:
                request.session[ACTIVE_ORGANIZATION_SESSION_KEY] = membership.organization_id
            else:
                request.session.pop(ACTIVE_ORGANIZATION_SESSION_KEY, None)

        if membership:
            request.active_membership = membership
            request.active_organization = membership.organization
        else:
            request.active_membership = None
            request.active_organization = None


class OrganizationService:
    @staticmethod
    def list_user_memberships(user):
        return MembershipRepository.list_for_user(user)

    @staticmethod
    def build_unique_slug(name):
        base_slug = slugify(name) or 'organization'
        candidate = base_slug
        suffix = 2

        while Organization.objects.filter(slug=candidate).exists():
            candidate = f'{base_slug}-{suffix}'
            suffix += 1

        return candidate

    @staticmethod
    @transaction.atomic
    def create_organization_for_user(*, user, name, segment, team_size):
        organization = OrganizationRepository.create(
            name=name,
            slug=OrganizationService.build_unique_slug(name),
            segment=segment,
            team_size=team_size,
            created_by=user,
        )
        MembershipRepository.create(
            user=user,
            organization=organization,
            role=OrganizationMembership.Role.OWNER,
            invited_by=user,
        )
        return organization

    @staticmethod
    def switch_active_organization(*, request, user, organization_public_id):
        membership = MembershipRepository.get_for_user_and_org_public_id(user, organization_public_id)
        if membership is None:
            raise PermissionDenied('Você não pode ativar uma organização da qual não faz parte.')

        ActiveOrganizationService.set_active_organization(request, membership.organization)
        return membership.organization


class InviteService:
    ROLE_PREFIX_MAP = {
        OrganizationInvite.TargetRole.ADMIN: 'ADM',
        OrganizationInvite.TargetRole.USER: 'USR',
    }
    CODE_PATTERN = re.compile(r'^(ADM|USR) [A-Z0-9]{8}$')

    @classmethod
    def normalize_code(cls, code):
        normalized = code.strip().upper().replace('-', ' ')
        normalized = re.sub(r'\s+', ' ', normalized)
        return normalized

    @classmethod
    def ensure_organization_access(cls, *, user, organization):
        membership = MembershipRepository.get_for_user_and_organization(user, organization)
        if membership is None:
            raise PermissionDenied('Você não faz parte desta organização.')
        return membership

    @classmethod
    def ensure_invite_management_permission(cls, *, user, organization):
        membership = cls.ensure_organization_access(user=user, organization=organization)
        if not membership.can_manage_invites:
            raise PermissionDenied('Somente proprietários e administradores podem gerenciar convites.')
        return membership

    @classmethod
    def expire_outdated_invites(cls, organization):
        InviteRepository.expire_outdated_for_organization(organization, timezone.now())

    @classmethod
    def generate_unique_code(cls, target_role):
        prefix = cls.ROLE_PREFIX_MAP[target_role]
        alphabet = string.ascii_uppercase + string.digits

        for _ in range(20):
            random_part = ''.join(random.choice(alphabet) for _ in range(8))
            code = f'{prefix} {random_part}'
            if InviteRepository.get_by_code(code) is None:
                return code

        raise ValidationError('Não foi possível gerar um código de convite único. Tente novamente.')

    @classmethod
    def generate_invite(cls, *, user, organization, target_role):
        cls.ensure_invite_management_permission(user=user, organization=organization)
        cls.expire_outdated_invites(organization)

        code = cls.generate_unique_code(target_role)
        return InviteRepository.create(
            organization=organization,
            code=code,
            target_role=target_role,
            created_by=user,
        )

    @classmethod
    @transaction.atomic
    def redeem_invite(cls, *, request, user, raw_code):
        code = cls.normalize_code(raw_code)

        if not cls.CODE_PATTERN.match(code):
            raise ValidationError('Informe um código de convite válido.')

        invite = InviteRepository.get_by_code(code)
        if invite is None:
            raise ValidationError('Este código de convite não foi encontrado.')

        cls.expire_outdated_invites(invite.organization)
        invite.refresh_from_db()

        if invite.status == OrganizationInvite.Status.EXPIRED:
            raise ValidationError('Este código de convite expirou.')
        if invite.status == OrganizationInvite.Status.USED:
            raise ValidationError('Este código de convite já foi usado.')

        existing_membership = MembershipRepository.get_for_user_and_organization(user, invite.organization)
        if existing_membership and existing_membership.is_active:
            raise ValidationError('Você já faz parte desta organização.')

        if existing_membership:
            existing_membership.role = invite.target_role
            existing_membership.is_active = True
            existing_membership.invited_by = invite.created_by
            existing_membership.save(update_fields=['role', 'is_active', 'invited_by', 'updated_at'])
            membership = existing_membership
        else:
            membership = MembershipRepository.create(
                user=user,
                organization=invite.organization,
                role=invite.target_role,
                invited_by=invite.created_by,
            )

        invite.status = OrganizationInvite.Status.USED
        invite.used_by = user
        invite.redeemed_at = timezone.now()
        invite.save(update_fields=['status', 'used_by', 'redeemed_at', 'updated_at'])

        ActiveOrganizationService.set_active_organization(request, membership.organization)
        return membership
