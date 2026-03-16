from django.db import migrations, models

import common.fields


def encrypt_existing_emails(apps, schema_editor):
    from common.encryption import build_email_lookup, normalize_email_address

    User = apps.get_model('accounts', 'User')

    for user in User.objects.all().iterator():
        normalized_email = normalize_email_address(user.email)
        user.email = normalized_email
        user.email_lookup = build_email_lookup(normalized_email)
        user.username = user.email_lookup
        user.save(update_fields=['email', 'email_lookup', 'username'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='user',
            options={'ordering': ('full_name', 'email_lookup')},
        ),
        migrations.AddField(
            model_name='user',
            name='email_lookup',
            field=models.CharField(blank=True, editable=False, max_length=64, null=True),
        ),
        migrations.AlterField(
            model_name='user',
            name='email',
            field=common.fields.EncryptedTextField(unique=True),
        ),
        migrations.RunPython(encrypt_existing_emails, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='user',
            name='email_lookup',
            field=models.CharField(editable=False, max_length=64, unique=True),
        ),
    ]
