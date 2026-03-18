import json
from urllib import error, parse, request

from django.conf import settings

from bot_conversa.constants import (
    BOT_CONVERSA_CONTACT_BY_PHONE_PATH_TEMPLATE,
    BOT_CONVERSA_CONTACTS_PATH,
    BOT_CONVERSA_CONTACTS_LIST_PATH,
    BOT_CONVERSA_FLOWS_PATH,
    BOT_CONVERSA_SUBSCRIBER_TAG_PATH_TEMPLATE,
    BOT_CONVERSA_TAGS_PATH,
    BOT_CONVERSA_SEND_MESSAGE_PATH_TEMPLATE,
    BOT_CONVERSA_SEND_FLOW_PATH_TEMPLATE,
    DEFAULT_REMOTE_CONTACT_MAX_PAGES,
)
from bot_conversa.exceptions import BotConversaApiError


class BotConversaClient:
    def __init__(self, *, api_key, base_url=None, timeout=None, auth_header=None):
        self.api_key = api_key
        self.base_url = (base_url or settings.BOT_CONVERSA_API_BASE_URL).rstrip('/')
        self.timeout = timeout or settings.BOT_CONVERSA_API_TIMEOUT
        self.auth_header = auth_header or settings.BOT_CONVERSA_API_AUTH_HEADER

    def list_flows(self):
        payload = self._request('GET', BOT_CONVERSA_FLOWS_PATH)
        flow_items = self._extract_collection(payload, fallback_keys=('flows', 'results', 'data'))

        normalized_flows = []
        for flow in flow_items:
            if not isinstance(flow, dict):
                continue
            normalized_flows.append(
                {
                    'external_flow_id': str(flow.get('id') or flow.get('flow_id') or flow.get('uuid') or ''),
                    'name': flow.get('name') or flow.get('title') or 'Fluxo sem nome',
                    'status': (flow.get('status') or 'unknown').lower(),
                    'description': flow.get('description') or flow.get('summary') or '',
                    'raw_payload': flow,
                }
            )

        return [flow for flow in normalized_flows if flow['external_flow_id']]

    def list_tags(self):
        payload = self._request('GET', BOT_CONVERSA_TAGS_PATH)
        tag_items = self._extract_collection(payload, fallback_keys=('results', 'tags', 'data'))

        normalized_tags = []
        for tag in tag_items:
            if not isinstance(tag, dict):
                continue
            normalized_tags.append(
                {
                    'external_tag_id': str(tag.get('id') or tag.get('tag_id') or tag.get('uuid') or ''),
                    'name': (tag.get('name') or tag.get('title') or '').strip(),
                    'raw_payload': tag,
                }
            )

        return [tag for tag in normalized_tags if tag['external_tag_id'] and tag['name']]

    def list_contacts(self, *, search='', page=1, max_pages=DEFAULT_REMOTE_CONTACT_MAX_PAGES):
        contacts = []
        current_page = max(int(page or 1), 1)
        total_pages_loaded = 0

        while current_page and total_pages_loaded < max(int(max_pages or 1), 1):
            payload = self._request('GET', BOT_CONVERSA_CONTACTS_LIST_PATH, query={'page': current_page})
            page_contacts = self._extract_collection(payload, fallback_keys=('results', 'subscribers', 'contacts', 'data'))
            contacts.extend(
                self._normalize_contact_payload(contact)
                for contact in page_contacts
                if isinstance(contact, dict)
            )

            next_page = self._extract_next_page(payload)
            if next_page is None or next_page == current_page:
                break

            current_page = next_page
            total_pages_loaded += 1

        if search:
            normalized_search = search.strip().lower()
            normalized_phone_search = self._normalize_api_phone(search)
            contacts = [
                contact
                for contact in contacts
                if normalized_search in (contact['name'] or '').lower()
                or (normalized_phone_search and normalized_phone_search in self._normalize_api_phone(contact['phone']))
            ]

        return contacts

    def search_contact_by_phone(self, *, phone):
        normalized_phone = self._normalize_api_phone(phone)
        path = BOT_CONVERSA_CONTACT_BY_PHONE_PATH_TEMPLATE.format(
            phone=parse.quote(normalized_phone, safe='+'),
        )
        payload = self._request('GET', path, allow_not_found=True)
        if payload is None:
            return None
        normalized_contact = self._normalize_contact_payload(payload)
        return normalized_contact if normalized_contact['external_subscriber_id'] else None

    def create_contact(self, *, first_name, last_name, phone):
        first_name = (first_name or '').strip() or 'Contato'
        last_name = (last_name or '').strip() or 'SemSobrenome'
        payload = {
            'first_name': first_name,
            'last_name': last_name,
            'phone': self._normalize_api_phone(phone),
            'has_opt_in_whatsapp': True,
        }
        response_payload = self._request('POST', BOT_CONVERSA_CONTACTS_PATH, payload=payload)
        normalized_contact = self._normalize_contact_payload(response_payload)

        if not normalized_contact['external_subscriber_id']:
            raise BotConversaApiError('O Bot Conversa nao retornou um identificador de subscriber.')

        return normalized_contact

    def send_flow(self, *, flow_id, subscriber_id):
        path = BOT_CONVERSA_SEND_FLOW_PATH_TEMPLATE.format(subscriber_id=subscriber_id)
        payload = self._request('POST', path, payload={'flow': int(flow_id)})

        return {
            'status': payload.get('status') or payload.get('result') or 'accepted',
            'message_id': str(payload.get('id') or payload.get('message_id') or ''),
            'raw_payload': payload,
        }

    def add_tag_to_subscriber(self, *, subscriber_id, tag_id):
        path = BOT_CONVERSA_SUBSCRIBER_TAG_PATH_TEMPLATE.format(
            subscriber_id=subscriber_id,
            tag_id=tag_id,
        )
        payload = self._request('POST', path, payload={})
        return {
            'status': payload.get('status') or payload.get('result') or 'created',
            'raw_payload': payload,
        }

    def remove_tag_from_subscriber(self, *, subscriber_id, tag_id):
        path = BOT_CONVERSA_SUBSCRIBER_TAG_PATH_TEMPLATE.format(
            subscriber_id=subscriber_id,
            tag_id=tag_id,
        )
        payload = self._request('DELETE', path, payload={})
        return {
            'status': payload.get('status') or payload.get('result') or 'deleted',
            'raw_payload': payload,
        }

    def send_message(self, *, subscriber_id, value, message_type='text'):
        path = BOT_CONVERSA_SEND_MESSAGE_PATH_TEMPLATE.format(subscriber_id=subscriber_id)
        payload = self._request(
            'POST',
            path,
            payload={
                'type': message_type,
                'value': value,
            },
        )

        return {
            'status': payload.get('status') or payload.get('result') or 'accepted',
            'message_id': str(payload.get('id') or payload.get('message_id') or ''),
            'raw_payload': payload,
        }

    def _request(self, method, path, *, query=None, payload=None, allow_not_found=False):
        url = f'{self.base_url}/{path.lstrip("/")}'
        if query:
            encoded_query = parse.urlencode(query, doseq=True)
            url = f'{url}?{encoded_query}'

        body = None
        headers = {
            'Accept': 'application/json',
            self.auth_header: self.api_key,
        }
        if payload is not None:
            body = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'

        api_request = request.Request(url, data=body, headers=headers, method=method.upper())

        try:
            with request.urlopen(api_request, timeout=self.timeout) as api_response:
                raw_response = api_response.read().decode('utf-8')
                return self._decode_json(raw_response)
        except error.HTTPError as exc:
            if allow_not_found and exc.code == 404:
                return None

            raw_error = exc.read().decode('utf-8')
            error_payload = self._decode_json(raw_error)
            message = (
                error_payload.get('detail')
                or error_payload.get('message')
                or error_payload.get('error')
                or raw_error.strip()
                or f'A requisicao ao Bot Conversa falhou com status {exc.code}.'
            )
            raise BotConversaApiError(message) from exc
        except error.URLError as exc:
            raise BotConversaApiError('O Bot Conversa esta indisponivel no momento. Tente novamente.') from exc

    @staticmethod
    def _decode_json(raw_payload):
        if not raw_payload:
            return {}

        try:
            return json.loads(raw_payload)
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _extract_collection(payload, *, fallback_keys):
        if isinstance(payload, list):
            return payload

        if isinstance(payload, dict):
            for key in fallback_keys:
                if isinstance(payload.get(key), list):
                    return payload[key]

        return []

    @staticmethod
    def _extract_next_page(payload):
        if not isinstance(payload, dict):
            return None

        next_url = payload.get('next')
        if not next_url:
            return None

        parsed_url = parse.urlparse(next_url)
        query_params = parse.parse_qs(parsed_url.query)
        next_page = query_params.get('page', [None])[0]

        try:
            return int(next_page) if next_page else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_contact_payload(payload):
        first_name = (payload.get('first_name') or '').strip()
        last_name = (payload.get('last_name') or '').strip()
        full_name = (
            payload.get('name')
            or payload.get('full_name')
            or ' '.join(part for part in [first_name, last_name] if part)
        )
        tag_names = BotConversaClient._normalize_tag_names(payload.get('tags'))

        return {
            'external_subscriber_id': str(payload.get('id') or payload.get('subscriber_id') or payload.get('uuid') or ''),
            'name': full_name,
            'first_name': first_name,
            'last_name': last_name,
            'phone': payload.get('phone') or payload.get('mobile') or '',
            'email': payload.get('email') or '',
            'status': (payload.get('status') or 'active').lower(),
            'tags_label': ', '.join(tag_names),
            'tag_names': tag_names,
            'raw_payload': payload,
        }

    @staticmethod
    def _normalize_api_phone(phone):
        raw_phone = (phone or '').strip()
        if raw_phone.startswith('+'):
            return '+' + ''.join(character for character in raw_phone[1:] if character.isdigit())
        return ''.join(character for character in raw_phone if character.isdigit())

    @staticmethod
    def _normalize_tag_names(raw_tags):
        if isinstance(raw_tags, list):
            normalized_tags = []
            for tag in raw_tags:
                if isinstance(tag, dict):
                    tag_name = tag.get('name') or tag.get('title') or tag.get('label') or ''
                else:
                    tag_name = str(tag)
                tag_name = str(tag_name).strip()
                if tag_name:
                    normalized_tags.append(tag_name)
            return normalized_tags
        if isinstance(raw_tags, str):
            return [part.strip() for part in raw_tags.split(',') if part.strip()]
        return []
