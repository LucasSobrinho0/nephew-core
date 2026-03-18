from django.urls import path

from bot_conversa.views import (
    BotConversaBulkPersonSyncView,
    BotConversaBulkRemoteContactSaveView,
    BotConversaContactsView,
    BotConversaDashboardView,
    BotConversaDispatchAudienceView,
    BotConversaDispatchCreateView,
    BotConversaDispatchDetailView,
    BotConversaDispatchProcessView,
    BotConversaDispatchesView,
    BotConversaFlowRefreshView,
    BotConversaFlowsView,
    BotConversaPeopleView,
    BotConversaPersonCreateView,
    BotConversaPersonSyncView,
    BotConversaRemoteContactSaveView,
    BotConversaTagAssignView,
    BotConversaTagRefreshView,
    BotConversaTagsView,
)

app_name = 'bot_conversa'

urlpatterns = [
    path('apps/bot-conversa/', BotConversaDashboardView.as_view(), name='dashboard'),
    path('apps/bot-conversa/people/', BotConversaPeopleView.as_view(), name='people'),
    path('apps/bot-conversa/people/create/', BotConversaPersonCreateView.as_view(), name='create_person'),
    path('apps/bot-conversa/people/sync/', BotConversaPersonSyncView.as_view(), name='sync_person'),
    path('apps/bot-conversa/people/sync/bulk/', BotConversaBulkPersonSyncView.as_view(), name='sync_people_bulk'),
    path('apps/bot-conversa/contacts/', BotConversaContactsView.as_view(), name='contacts'),
    path('apps/bot-conversa/contacts/save/', BotConversaRemoteContactSaveView.as_view(), name='save_remote_contact'),
    path('apps/bot-conversa/contacts/save/bulk/', BotConversaBulkRemoteContactSaveView.as_view(), name='save_remote_contacts_bulk'),
    path('apps/bot-conversa/tags/', BotConversaTagsView.as_view(), name='tags'),
    path('apps/bot-conversa/tags/refresh/', BotConversaTagRefreshView.as_view(), name='refresh_tags'),
    path('apps/bot-conversa/tags/assign/', BotConversaTagAssignView.as_view(), name='assign_tag'),
    path('apps/bot-conversa/flows/', BotConversaFlowsView.as_view(), name='flows'),
    path('apps/bot-conversa/flows/refresh/', BotConversaFlowRefreshView.as_view(), name='refresh_flows'),
    path('apps/bot-conversa/dispatches/', BotConversaDispatchesView.as_view(), name='dispatches'),
    path('apps/bot-conversa/dispatches/create/', BotConversaDispatchCreateView.as_view(), name='create_dispatch'),
    path('apps/bot-conversa/dispatches/audience/', BotConversaDispatchAudienceView.as_view(), name='dispatch_audience'),
    path(
        'apps/bot-conversa/dispatches/<uuid:dispatch_public_id>/',
        BotConversaDispatchDetailView.as_view(),
        name='dispatch_detail',
    ),
    path(
        'apps/bot-conversa/dispatches/<uuid:dispatch_public_id>/process/',
        BotConversaDispatchProcessView.as_view(),
        name='dispatch_process',
    ),
]
