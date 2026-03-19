from django.urls import path

from dispatch_flow.views import (
    DispatchFlowBotConversaCreateView,
    DispatchFlowGmailCreateView,
    DispatchFlowView,
)

app_name = 'dispatch_flow'

urlpatterns = [
    path('fluxo-disparo/', DispatchFlowView.as_view(), name='index'),
    path(
        'fluxo-disparo/bot-conversa/create/',
        DispatchFlowBotConversaCreateView.as_view(),
        name='create_bot_conversa_dispatch',
    ),
    path(
        'fluxo-disparo/gmail/create/',
        DispatchFlowGmailCreateView.as_view(),
        name='create_gmail_dispatch',
    ),
]
