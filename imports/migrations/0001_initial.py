from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('organizations', '0002_alter_organization_segment_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ImportJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('entity_type', models.CharField(choices=[('people', 'Pessoas'), ('companies', 'Empresas')], max_length=24)),
                ('status', models.CharField(choices=[('pending', 'Pendente'), ('running', 'Em andamento'), ('completed', 'Concluido'), ('completed_with_errors', 'Concluido com erros'), ('failed', 'Falhou')], default='pending', max_length=32)),
                ('source_filename', models.CharField(max_length=255)),
                ('stored_file_path', models.CharField(blank=True, max_length=512)),
                ('total_rows', models.PositiveIntegerField(default=0)),
                ('processed_rows', models.PositiveIntegerField(default=0)),
                ('success_rows', models.PositiveIntegerField(default=0)),
                ('failed_rows', models.PositiveIntegerField(default=0)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('error_summary', models.CharField(blank=True, max_length=255)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_import_jobs', to=settings.AUTH_USER_MODEL)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='import_jobs', to='organizations.organization')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='updated_import_jobs', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ('-created_at',)},
        ),
        migrations.CreateModel(
            name='ImportJobItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('row_number', models.PositiveIntegerField()),
                ('status', models.CharField(choices=[('pending', 'Pendente'), ('success', 'Sucesso'), ('failed', 'Falhou')], default='pending', max_length=16)),
                ('message', models.CharField(blank=True, max_length=255)),
                ('raw_payload', models.JSONField(blank=True, default=dict)),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='imports.importjob')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='import_job_items', to='organizations.organization')),
            ],
            options={'ordering': ('row_number',)},
        ),
        migrations.AddIndex(
            model_name='importjob',
            index=models.Index(fields=['organization', 'entity_type', 'status'], name='imports_imp_organiz_4f8887_idx'),
        ),
        migrations.AddConstraint(
            model_name='importjobitem',
            constraint=models.UniqueConstraint(fields=('job', 'row_number'), name='unique_import_job_row_number'),
        ),
        migrations.AddIndex(
            model_name='importjobitem',
            index=models.Index(fields=['organization', 'job', 'status'], name='imports_imp_organiz_f039c5_idx'),
        ),
    ]
