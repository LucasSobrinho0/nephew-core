from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people', '0005_person_apollo_person_id_and_optional_phone'),
        ('hubspot_integration', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='hubspotdeal',
            name='persons',
            field=models.ManyToManyField(blank=True, related_name='hubspot_deals', to='people.person'),
        ),
    ]
