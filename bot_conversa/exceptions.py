class BotConversaError(Exception):
    pass


class BotConversaConfigurationError(BotConversaError):
    pass


class BotConversaApiError(BotConversaError):
    pass
