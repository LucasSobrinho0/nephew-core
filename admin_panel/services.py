import math
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from urllib.parse import urlencode

from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from admin_panel.repositories import AdminAccessLogRepository

SYSTEM_ADMIN_GROUP_NAME = 'Admin'
SYSTEM_USER_GROUP_NAME = 'User'


def get_client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class AdminAuthorizationService:
    @staticmethod
    def has_panel_access(user):
        if not getattr(user, 'is_authenticated', False):
            return False
        return user.groups.filter(name=SYSTEM_ADMIN_GROUP_NAME).exists()

    @staticmethod
    def ensure_panel_access(user):
        if not AdminAuthorizationService.has_panel_access(user):
            raise PermissionDenied('Somente usuarios do grupo Admin podem acessar o Painel Admin.')


class AdminAccessAuditService:
    @staticmethod
    def _ensure_session_key(request):
        session_key = request.session.session_key
        if not session_key:
            request.session.save()
            session_key = request.session.session_key or ''
        return session_key

    @staticmethod
    def _create_access_log(*, request, user, session_key):
        return AdminAccessLogRepository.create(
            user=user,
            logged_in_by=user,
            session_key=session_key,
            ip_address=get_client_ip(request),
            user_agent=(request.META.get('HTTP_USER_AGENT', '') or '')[:255],
            logged_in_at=timezone.now(),
        )

    @staticmethod
    def record_login(*, request, user):
        session_key = AdminAccessAuditService._ensure_session_key(request)
        return AdminAccessAuditService._create_access_log(
            request=request,
            user=user,
            session_key=session_key,
        )

    @staticmethod
    def sync_authenticated_session(*, request):
        user = request.user
        session_key = AdminAccessAuditService._ensure_session_key(request)
        current_ip = get_client_ip(request)
        current_user_agent = (request.META.get('HTTP_USER_AGENT', '') or '')[:255]
        access_log = AdminAccessLogRepository.get_latest_open_by_session_key(session_key)

        if access_log is None:
            return AdminAccessAuditService._create_access_log(
                request=request,
                user=user,
                session_key=session_key,
            )

        if access_log.user_id != user.id or access_log.ip_address != current_ip:
            access_log.logged_out_at = timezone.now()
            access_log.logged_out_by = user
            access_log.save(update_fields=['logged_out_at', 'logged_out_by'])
            return AdminAccessAuditService._create_access_log(
                request=request,
                user=user,
                session_key=session_key,
            )

        if access_log.user_agent != current_user_agent:
            access_log.user_agent = current_user_agent
            access_log.save(update_fields=['user_agent'])

        return access_log

    @staticmethod
    def record_logout(*, request):
        if not request.user.is_authenticated:
            return None

        access_log = AdminAccessLogRepository.get_latest_open_by_session_key(request.session.session_key or '')
        if access_log is None:
            return None

        access_log.logged_out_at = timezone.now()
        access_log.logged_out_by = request.user
        access_log.save(update_fields=['logged_out_at', 'logged_out_by'])
        return access_log


class AdminPanelNavigationService:
    @staticmethod
    def build_navigation_items():
        return [
            {
                'key': 'overview',
                'label': 'Visao geral',
                'route_name': 'admin_panel:index',
                'icon_class': 'bi bi-speedometer2',
            },
            {
                'key': 'ip_logs',
                'label': 'IPs',
                'route_name': 'admin_panel:ip_logs',
                'icon_class': 'bi bi-router-fill',
            },
        ]


class AdminPanelOverviewService:
    @staticmethod
    def build_summary():
        latest_entry = AdminAccessLogRepository.latest_entry()
        return {
            'total_access_logs': AdminAccessLogRepository.count_all(),
            'open_sessions': AdminAccessLogRepository.count_open_sessions(),
            'latest_entry': latest_entry,
            'top_ip_addresses': AdminAccessLogRepository.top_ip_addresses(limit=5),
        }


@dataclass(frozen=True)
class KeysetPageResult:
    records: list
    page_size: int
    total_count: int
    has_previous: bool
    has_next: bool
    previous_cursor: str
    next_cursor: str


class AdminAccessLogPaginationService:
    @staticmethod
    def encode_cursor(*, logged_in_at, object_id):
        raw_value = f'{logged_in_at.isoformat()}|{object_id}'
        return urlsafe_b64encode(raw_value.encode('utf-8')).decode('ascii')

    @staticmethod
    def decode_cursor(cursor_value):
        if not cursor_value:
            return None
        try:
            decoded_value = urlsafe_b64decode(cursor_value.encode('ascii')).decode('utf-8')
            logged_in_at, object_id = decoded_value.split('|', 1)
            return {
                'logged_in_at': timezone.datetime.fromisoformat(logged_in_at),
                'id': int(object_id),
            }
        except (ValueError, TypeError):
            return None

    @staticmethod
    def build_page(*, page_size, cursor_value='', direction='next'):
        total_count = AdminAccessLogRepository.count_all()
        cursor = AdminAccessLogPaginationService.decode_cursor(cursor_value)
        before_cursor = cursor if direction == 'previous' else None
        after_cursor = cursor if direction != 'previous' else None

        page_records, loaded_from_previous = AdminAccessLogRepository.list_page(
            page_size=page_size,
            after_cursor=after_cursor,
            before_cursor=before_cursor,
        )
        has_extra_record = len(page_records) > page_size
        records = page_records[:page_size]

        if loaded_from_previous:
            has_previous = has_extra_record
            has_next = bool(cursor)
        else:
            has_previous = bool(cursor)
            has_next = has_extra_record

        previous_cursor = ''
        next_cursor = ''
        if records:
            first_record = records[0]
            last_record = records[-1]
            if has_previous:
                previous_cursor = AdminAccessLogPaginationService.encode_cursor(
                    logged_in_at=first_record.logged_in_at,
                    object_id=first_record.id,
                )
            if has_next:
                next_cursor = AdminAccessLogPaginationService.encode_cursor(
                    logged_in_at=last_record.logged_in_at,
                    object_id=last_record.id,
                )

        return KeysetPageResult(
            records=records,
            page_size=page_size,
            total_count=total_count,
            has_previous=has_previous,
            has_next=has_next,
            previous_cursor=previous_cursor,
            next_cursor=next_cursor,
        )


class AdminPanelQueryService:
    @staticmethod
    def build_ip_log_list(*, page_size, cursor_value='', direction='next'):
        return AdminAccessLogPaginationService.build_page(
            page_size=page_size,
            cursor_value=cursor_value,
            direction=direction,
        )

    @staticmethod
    def build_cursor_url(*, base_url, page_size, cursor_value, direction):
        if not cursor_value:
            return ''
        return f'{base_url}?{urlencode({"per_page": page_size, "cursor": cursor_value, "direction": direction})}'


class AdminBootstrapService:
    @staticmethod
    def ensure_system_groups():
        Group.objects.get_or_create(name=SYSTEM_ADMIN_GROUP_NAME)
        Group.objects.get_or_create(name=SYSTEM_USER_GROUP_NAME)
