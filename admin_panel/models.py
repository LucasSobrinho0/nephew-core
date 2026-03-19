from django.conf import settings
from django.db import models
from django.utils import timezone


class AdminAccessLogQuerySet(models.QuerySet):
    def with_related_users(self):
        return self.select_related('user', 'logged_in_by', 'logged_out_by')

    def ordered(self):
        return self.order_by('-logged_in_at', '-id')

    def open_sessions(self):
        return self.filter(logged_out_at__isnull=True)


class AdminAccessLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='admin_access_logs',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    logged_in_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='admin_login_events',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    logged_out_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='admin_logout_events',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    session_key = models.CharField(max_length=40, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    logged_in_at = models.DateTimeField(default=timezone.now)
    logged_out_at = models.DateTimeField(null=True, blank=True)

    objects = AdminAccessLogQuerySet.as_manager()

    class Meta:
        ordering = ('-logged_in_at', '-id')
        indexes = [
            models.Index(fields=('logged_in_at', 'id')),
            models.Index(fields=('session_key',)),
            models.Index(fields=('user', 'logged_in_at')),
        ]

    def __str__(self):
        identity = self.user.full_name if self.user else 'Usuario removido'
        return f'{identity} - {self.ip_address or "IP nao informado"}'

