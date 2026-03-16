from django.db import migrations


def backfill_person_bot_conversa_id(apps, schema_editor):
    Person = apps.get_model('people', 'Person')
    BotConversaContact = apps.get_model('bot_conversa', 'BotConversaContact')

    for contact_link in BotConversaContact.objects.select_related('person').all():
        if contact_link.person_id is None or not contact_link.external_subscriber_id:
            continue

        Person.objects.filter(
            pk=contact_link.person_id,
            bot_conversa_id__isnull=True,
        ).update(bot_conversa_id=contact_link.external_subscriber_id)


def revert_person_bot_conversa_id(apps, schema_editor):
    Person = apps.get_model('people', 'Person')
    BotConversaContact = apps.get_model('bot_conversa', 'BotConversaContact')

    subscriber_ids = list(
        BotConversaContact.objects.exclude(external_subscriber_id='').values_list('external_subscriber_id', flat=True)
    )
    if subscriber_ids:
        Person.objects.filter(bot_conversa_id__in=subscriber_ids).update(bot_conversa_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ('people', '0002_person_bot_conversa_id_and_more'),
        ('bot_conversa', '0003_alter_botconversacontact_sync_status_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_person_bot_conversa_id, revert_person_bot_conversa_id),
    ]
