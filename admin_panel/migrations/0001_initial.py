from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AdminAccessLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_key', models.CharField(blank=True, max_length=40)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.CharField(blank=True, max_length=255)),
                ('logged_in_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('logged_out_at', models.DateTimeField(blank=True, null=True)),
                ('logged_in_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='admin_login_events', to=settings.AUTH_USER_MODEL)),
                ('logged_out_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='admin_logout_events', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='admin_access_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-logged_in_at', '-id'),
                'indexes': [
                    models.Index(fields=['logged_in_at', 'id'], name='admin_panel_logged__f3c9bb_idx'),
                    models.Index(fields=['session_key'], name='admin_panel_session_7ce835_idx'),
                    models.Index(fields=['user', 'logged_in_at'], name='admin_panel_user_id_16b7d2_idx'),
                ],
            },
        ),
    ]

