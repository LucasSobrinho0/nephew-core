from django.contrib import admin

from bot_conversa.models import (
    BotConversaContact,
    BotConversaFlowCache,
    BotConversaFlowDispatch,
    BotConversaFlowDispatchItem,
    BotConversaPersonTag,
    BotConversaSyncLog,
    BotConversaTag,
)


@admin.register(BotConversaContact)
class BotConversaContactAdmin(admin.ModelAdmin):
    list_display = ('person', 'organization', 'external_subscriber_id', 'sync_status', 'last_synced_at')
    list_filter = ('organization', 'sync_status')
    search_fields = ('person__first_name', 'person__last_name', 'external_subscriber_id', 'phone')


@admin.register(BotConversaFlowCache)
class BotConversaFlowCacheAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'status', 'last_synced_at')
    list_filter = ('organization', 'status')
    search_fields = ('name', 'external_flow_id')


@admin.register(BotConversaTag)
class BotConversaTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'external_tag_id', 'last_synced_at')
    list_filter = ('organization',)
    search_fields = ('name', 'external_tag_id')


@admin.register(BotConversaPersonTag)
class BotConversaPersonTagAdmin(admin.ModelAdmin):
    list_display = ('person', 'tag', 'organization', 'sync_status', 'last_synced_at')
    list_filter = ('organization', 'sync_status', 'tag')
    search_fields = ('person__first_name', 'person__last_name', 'tag__name', 'external_subscriber_id')


@admin.register(BotConversaFlowDispatch)
class BotConversaFlowDispatchAdmin(admin.ModelAdmin):
    list_display = ('flow_name', 'organization', 'status', 'total_items', 'success_items', 'failed_items', 'created_at')
    list_filter = ('organization', 'status')
    search_fields = ('flow_name', 'external_flow_id')


@admin.register(BotConversaFlowDispatchItem)
class BotConversaFlowDispatchItemAdmin(admin.ModelAdmin):
    list_display = ('dispatch', 'target_name', 'target_phone', 'status', 'attempt_count', 'sent_at')
    list_filter = ('organization', 'status')
    search_fields = ('target_name', 'target_phone', 'external_subscriber_id')


@admin.register(BotConversaSyncLog)
class BotConversaSyncLogAdmin(admin.ModelAdmin):
    list_display = ('organization', 'action', 'outcome', 'person', 'created_at')
    list_filter = ('organization', 'action', 'outcome')
    search_fields = ('person__first_name', 'person__last_name', 'message')
