import base64
import json
from email.mime.text import MIMEText

from gmail_integration.constants import GMAIL_SEND_SCOPE
from gmail_integration.exceptions import GmailApiError, GmailConfigurationError


class GmailApiGateway:
    def __init__(self, *, token_payload, required_scopes=None):
        self.token_payload = token_payload
        self.required_scopes = required_scopes or [GMAIL_SEND_SCOPE]

    def build_service(self):
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise GmailConfigurationError(
                'As dependencias do Gmail nao estao instaladas. Adicione google-api-python-client, google-auth-oauthlib e google-auth.'
            ) from exc

        credential_data = dict(self.token_payload)
        credentials = Credentials.from_authorized_user_info(credential_data, self.required_scopes)

        current_scopes = set(credentials.scopes or credential_data.get('scopes') or [])
        if not set(self.required_scopes).issubset(current_scopes):
            raise GmailConfigurationError('O token informado nao possui o escopo necessario para envio de email.')

        refreshed_token_payload = None
        if not credentials.valid:
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                refreshed_token_payload = json.loads(credentials.to_json())
            else:
                raise GmailConfigurationError('O token do Gmail expirou e nao possui refresh token para renovacao automatica.')

        service = build('gmail', 'v1', credentials=credentials, cache_discovery=False)
        return service, refreshed_token_payload

    def send_email(self, *, recipient_email, subject, body, cc_emails=None):
        service, refreshed_token_payload = self.build_service()
        raw_message = self.build_raw_message(
            recipient_email=recipient_email,
            subject=subject,
            body=body,
            cc_emails=cc_emails or [],
        )

        try:
            response = (
                service.users()
                .messages()
                .send(userId='me', body={'raw': raw_message})
                .execute()
            )
        except Exception as exc:
            raise GmailApiError(str(exc)) from exc

        return {
            'message_id': response.get('id', ''),
            'thread_id': response.get('threadId', ''),
            'refreshed_token_payload': refreshed_token_payload,
        }

    @staticmethod
    def build_raw_message(*, recipient_email, subject, body, cc_emails):
        message = MIMEText(body, _charset='utf-8')
        message['to'] = recipient_email
        message['subject'] = subject
        if cc_emails:
            message['cc'] = ', '.join(cc_emails)
        return base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
