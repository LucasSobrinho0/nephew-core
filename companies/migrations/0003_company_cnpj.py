from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('companies', '0002_apollo_company_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='cnpj',
            field=models.CharField(blank=True, db_index=True, default='', max_length=14),
        ),
        migrations.AddConstraint(
            model_name='company',
            constraint=models.UniqueConstraint(
                condition=~models.Q(cnpj=''),
                fields=('organization', 'cnpj'),
                name='unique_company_cnpj_per_organization',
            ),
        ),
    ]
