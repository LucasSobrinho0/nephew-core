from django.contrib import admin

from gmail_integration.models import GmailCredential, GmailDispatch, GmailDispatchRecipient, GmailTemplate

admin.site.register(GmailCredential)
admin.site.register(GmailTemplate)
admin.site.register(GmailDispatch)
admin.site.register(GmailDispatchRecipient)
