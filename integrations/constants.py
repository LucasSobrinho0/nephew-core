REVEAL_CONFIRMATION_WORD = 'mostrar'
API_KEY_CREDENTIAL_TYPE = 'api_key'
BOT_CONVERSA_APP_CODE = 'bot_conversa'

APP_NAVIGATION_ITEMS = {
    'bot_conversa': {
        'label': 'Bot Conversa',
        'icon_class': 'bi bi-chat-dots-fill',
        'route_name': 'bot_conversa:dashboard',
    },
    'apollo': {
        'label': 'Apollo',
        'icon_class': 'bi bi-broadcast-pin',
        'route_name': '',
    },
    'hubspot': {
        'label': 'HubSpot',
        'icon_class': 'bi bi-diagram-3-fill',
        'route_name': 'hubspot_integration:dashboard',
    },
    'gmail': {
        'label': 'Gmail',
        'icon_class': 'bi bi-envelope-paper-fill',
        'route_name': 'gmail_integration:dashboard',
    },
}
