from django.db import migrations


def update_bot_conversa_metadata(apps, schema_editor):
    AppCatalog = apps.get_model('integrations', 'AppCatalog')
    AppCatalog.objects.filter(code='bot_conversa').update(
        name='Bot Conversa',
        description='Messaging automation connector for contacts, flows, and dispatch operations.',
        icon_class='bi bi-chat-dots-fill',
    )


def revert_bot_conversa_metadata(apps, schema_editor):
    AppCatalog = apps.get_model('integrations', 'AppCatalog')
    AppCatalog.objects.filter(code='bot_conversa').update(
        name='BotConversa',
        description='Messaging automation connector prepared for campaign and chat workflows.',
        icon_class='bi bi-chat-dots-fill',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0002_seed_app_catalog'),
    ]

    operations = [
        migrations.RunPython(update_bot_conversa_metadata, revert_bot_conversa_metadata),
    ]
