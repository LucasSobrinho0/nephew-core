from django.db.models import Count, Q

from admin_panel.models import AdminAccessLog


class AdminAccessLogRepository:
    @staticmethod
    def create(**kwargs):
        return AdminAccessLog.objects.create(**kwargs)

    @staticmethod
    def get_latest_open_by_session_key(session_key):
        if not session_key:
            return None
        return (
            AdminAccessLog.objects.with_related_users()
            .open_sessions()
            .filter(session_key=session_key)
            .ordered()
            .first()
        )

    @staticmethod
    def get_latest_by_session_key(session_key):
        if not session_key:
            return None
        return (
            AdminAccessLog.objects.with_related_users()
            .filter(session_key=session_key)
            .ordered()
            .first()
        )

    @staticmethod
    def list_page(*, page_size, after_cursor=None, before_cursor=None):
        queryset = AdminAccessLog.objects.with_related_users().ordered()

        if after_cursor:
            queryset = queryset.filter(
                Q(logged_in_at__lt=after_cursor['logged_in_at'])
                | Q(logged_in_at=after_cursor['logged_in_at'], id__lt=after_cursor['id'])
            )
            return list(queryset[: page_size + 1]), False

        if before_cursor:
            queryset = queryset.filter(
                Q(logged_in_at__gt=before_cursor['logged_in_at'])
                | Q(logged_in_at=before_cursor['logged_in_at'], id__gt=before_cursor['id'])
            ).order_by('logged_in_at', 'id')
            records = list(queryset[: page_size + 1])
            records.reverse()
            return records, True

        return list(queryset[: page_size + 1]), False

    @staticmethod
    def count_all():
        return AdminAccessLog.objects.count()

    @staticmethod
    def count_open_sessions():
        return AdminAccessLog.objects.open_sessions().count()

    @staticmethod
    def latest_entry():
        return AdminAccessLog.objects.with_related_users().ordered().first()

    @staticmethod
    def top_ip_addresses(*, limit=5):
        return list(
            AdminAccessLog.objects.exclude(ip_address__isnull=True)
            .exclude(ip_address='')
            .values('ip_address')
            .annotate(total=Count('id'))
            .order_by('-total', 'ip_address')[:limit]
        )
