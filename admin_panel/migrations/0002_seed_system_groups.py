from django.db import migrations


def seed_system_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.get_or_create(name='Admin')
    Group.objects.get_or_create(name='User')


def unseed_system_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name__in=['Admin', 'User']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('admin_panel', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(seed_system_groups, unseed_system_groups),
    ]

