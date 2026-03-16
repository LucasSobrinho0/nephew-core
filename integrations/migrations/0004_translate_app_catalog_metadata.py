from django.db import migrations


CATALOG_UPDATES = {
    'apollo': {
        'description': 'Fluxos de prospeccao e enriquecimento para operacoes de vendas outbound.',
    },
    'hubspot': {
        'description': 'Sincronizacao de CRM e marketing para contatos, etapas de negocio e visibilidade do ciclo de vida.',
    },
    'gmail': {
        'description': 'Conectividade de e-mail para futuras sincronizacoes de caixa de entrada, registro de mensagens e acompanhamento de atividades.',
    },
    'bot_conversa': {
        'name': 'Bot Conversa',
        'description': 'Conector de automacao de mensagens para contatos, fluxos e operacoes de disparo.',
    },
}


CATALOG_REVERTS = {
    'apollo': {
        'description': 'Prospecting and enrichment workflows for outbound sales operations.',
    },
    'hubspot': {
        'description': 'CRM and marketing sync for contacts, deal stages, and lifecycle visibility.',
    },
    'gmail': {
        'description': 'Email connectivity for future inbox sync, message logging, and activity tracking.',
    },
    'bot_conversa': {
        'name': 'Bot Conversa',
        'description': 'Messaging automation connector for contacts, flows, and dispatch operations.',
    },
}


def apply_catalog_translations(apps, schema_editor):
    AppCatalog = apps.get_model('integrations', 'AppCatalog')
    for code, defaults in CATALOG_UPDATES.items():
        AppCatalog.objects.filter(code=code).update(**defaults)


def revert_catalog_translations(apps, schema_editor):
    AppCatalog = apps.get_model('integrations', 'AppCatalog')
    for code, defaults in CATALOG_REVERTS.items():
        AppCatalog.objects.filter(code=code).update(**defaults)


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0003_update_bot_conversa_metadata'),
    ]

    operations = [
        migrations.RunPython(apply_catalog_translations, revert_catalog_translations),
    ]
