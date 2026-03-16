from django.db import migrations


def seed_app_catalog(apps, schema_editor):
    AppCatalog = apps.get_model('integrations', 'AppCatalog')

    catalog_items = [
        {
            'code': 'apollo',
            'name': 'Apollo',
            'description': 'Prospecting and enrichment workflows for outbound sales operations.',
            'icon_class': 'bi bi-broadcast-pin',
            'sort_order': 10,
        },
        {
            'code': 'hubspot',
            'name': 'HubSpot',
            'description': 'CRM and marketing sync for contacts, deal stages, and lifecycle visibility.',
            'icon_class': 'bi bi-diagram-3-fill',
            'sort_order': 20,
        },
        {
            'code': 'gmail',
            'name': 'Gmail',
            'description': 'Email connectivity for future inbox sync, message logging, and activity tracking.',
            'icon_class': 'bi bi-envelope-paper-fill',
            'sort_order': 30,
        },
        {
            'code': 'bot_conversa',
            'name': 'BotConversa',
            'description': 'Messaging automation connector prepared for campaign and chat workflows.',
            'icon_class': 'bi bi-chat-dots-fill',
            'sort_order': 40,
        },
    ]

    for item in catalog_items:
        AppCatalog.objects.update_or_create(
            code=item['code'],
            defaults={
                'name': item['name'],
                'description': item['description'],
                'icon_class': item['icon_class'],
                'supports_api_key': True,
                'is_active': True,
                'sort_order': item['sort_order'],
            },
        )


def unseed_app_catalog(apps, schema_editor):
    AppCatalog = apps.get_model('integrations', 'AppCatalog')
    AppCatalog.objects.filter(code__in=['apollo', 'hubspot', 'gmail', 'bot_conversa']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_app_catalog, unseed_app_catalog),
    ]
