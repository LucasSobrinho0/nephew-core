from django.db import migrations


def update_gmail_catalog_metadata(apps, schema_editor):
    AppCatalog = apps.get_model('integrations', 'AppCatalog')
    AppCatalog.objects.filter(code='gmail').update(
        description='Email sending workspace with encrypted OAuth credentials, reusable templates, and tenant-safe dispatch history.',
        supports_api_key=False,
        icon_class='bi bi-envelope-paper-fill',
    )


def revert_gmail_catalog_metadata(apps, schema_editor):
    AppCatalog = apps.get_model('integrations', 'AppCatalog')
    AppCatalog.objects.filter(code='gmail').update(
        description='Email connectivity for future inbox sync, message logging, and activity tracking.',
        supports_api_key=True,
        icon_class='bi bi-envelope-paper-fill',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0005_alter_appcredentialaccessaudit_event_type_and_more'),
    ]

    operations = [
        migrations.RunPython(update_gmail_catalog_metadata, revert_gmail_catalog_metadata),
    ]
