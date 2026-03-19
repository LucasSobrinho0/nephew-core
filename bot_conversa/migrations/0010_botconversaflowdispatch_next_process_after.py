from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bot_conversa', '0009_alter_botconversaflowdispatch_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='botconversaflowdispatch',
            name='next_process_after',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
