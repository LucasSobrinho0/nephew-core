import json
from urllib import error, parse, request

from hubspot_integration.constants import (
    CONTACT_TO_COMPANY_ASSOCIATION_TYPE_ID,
    DEAL_TO_COMPANY_ASSOCIATION_TYPE_ID,
    DEAL_TO_CONTACT_ASSOCIATION_TYPE_ID,
    HUBSPOT_API_BASE_URL,
    HUBSPOT_COMPANIES_OBJECT_PATH,
    HUBSPOT_COMPANIES_SEARCH_PATH,
    HUBSPOT_CONTACTS_OBJECT_PATH,
    HUBSPOT_CONTACTS_SEARCH_PATH,
    HUBSPOT_DEALS_OBJECT_PATH,
    HUBSPOT_DEAL_PIPELINES_PATH,
    HUBSPOT_DEFAULT_TIMEOUT_SECONDS,
)
from hubspot_integration.exceptions import HubSpotApiError


class HubSpotClient:
    def __init__(self, *, api_key, base_url=HUBSPOT_API_BASE_URL, timeout=HUBSPOT_DEFAULT_TIMEOUT_SECONDS):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout

    def list_companies(self, *, limit=100):
        payload = self._request('GET', HUBSPOT_COMPANIES_OBJECT_PATH, query={'limit': limit, 'properties': 'name,website,phone,domain'})
        return [
            self._normalize_company_payload(item)
            for item in (payload.get('results') or [])
            if isinstance(item, dict)
        ]

    def list_contacts(self, *, limit=100):
        payload = self._request('GET', HUBSPOT_CONTACTS_OBJECT_PATH, query={'limit': limit, 'properties': 'firstname,lastname,email,phone,mobilephone,company,website'})
        return [
            self._normalize_contact_payload(item)
            for item in (payload.get('results') or [])
            if isinstance(item, dict)
        ]

    def list_deal_pipelines(self):
        payload = self._request('GET', HUBSPOT_DEAL_PIPELINES_PATH)
        return [
            {
                'hubspot_pipeline_id': str(item.get('id') or ''),
                'name': item.get('label') or item.get('displayOrder') or 'Pipeline sem nome',
                'object_type': 'deals',
                'raw_payload': item,
            }
            for item in (payload.get('results') or [])
            if isinstance(item, dict) and item.get('id')
        ]

    def create_or_get_company(self, *, name, website='', phone=''):
        search_result = self.search_company_by_name_or_website(name=name, website=website)
        if search_result is not None:
            return {'created': False, **search_result}

        properties = {'name': name}
        if website:
            properties['website'] = website
            properties['domain'] = self.extract_domain_from_website(website)
        if phone:
            properties['phone'] = phone

        response_payload = self._request('POST', HUBSPOT_COMPANIES_OBJECT_PATH, payload={'properties': properties})
        return {'created': True, **self._normalize_company_payload(response_payload)}

    def create_or_get_contact(self, *, first_name, last_name, email='', phone='', company_id=''):
        search_result = self.search_contact_by_email(email=email)
        if search_result is not None:
            return {'created': False, **search_result}

        properties = {}
        if first_name:
            properties['firstname'] = first_name
        if last_name:
            properties['lastname'] = last_name
        if email:
            properties['email'] = email
        if phone:
            properties['phone'] = phone

        if not (properties.get('email') or properties.get('firstname') or properties.get('lastname')):
            raise HubSpotApiError('HubSpot exige ao menos e-mail ou nome para criar contato.')

        payload = {'properties': properties}
        if company_id:
            payload['associations'] = [
                {
                    'to': {'id': company_id},
                    'types': [
                        {
                            'associationCategory': 'HUBSPOT_DEFINED',
                            'associationTypeId': CONTACT_TO_COMPANY_ASSOCIATION_TYPE_ID,
                        }
                    ],
                }
            ]

        response_payload = self._request('POST', HUBSPOT_CONTACTS_OBJECT_PATH, payload=payload)
        return {'created': True, **self._normalize_contact_payload(response_payload)}

    def create_deal(self, *, name, pipeline_id, stage_id, company_id, contact_ids, amount=''):
        associations = []
        for contact_id in contact_ids:
            associations.append(
                {
                    'to': {'id': contact_id},
                    'types': [
                        {
                            'associationCategory': 'HUBSPOT_DEFINED',
                            'associationTypeId': DEAL_TO_CONTACT_ASSOCIATION_TYPE_ID,
                        }
                    ],
                }
            )

        associations.append(
            {
                'to': {'id': company_id},
                'types': [
                    {
                        'associationCategory': 'HUBSPOT_DEFINED',
                        'associationTypeId': DEAL_TO_COMPANY_ASSOCIATION_TYPE_ID,
                    }
                ],
            }
        )

        properties = {'dealname': name, 'pipeline': pipeline_id}
        if stage_id:
            properties['dealstage'] = stage_id
        if amount:
            properties['amount'] = amount

        response_payload = self._request(
            'POST',
            HUBSPOT_DEALS_OBJECT_PATH,
            payload={'properties': properties, 'associations': associations},
        )
        return {
            'hubspot_deal_id': str(response_payload.get('id') or ''),
            'raw_payload': response_payload,
        }

    def search_company_by_name_or_website(self, *, name, website=''):
        filters = []
        if website:
            filters.append({'propertyName': 'domain', 'operator': 'EQ', 'value': self.extract_domain_from_website(website)})
        if name:
            filters.append({'propertyName': 'name', 'operator': 'EQ', 'value': name})

        for search_filter in filters:
            payload = {
                'filterGroups': [{'filters': [search_filter]}],
                'properties': ['name', 'website', 'phone', 'domain'],
                'limit': 1,
            }
            response_payload = self._request('POST', HUBSPOT_COMPANIES_SEARCH_PATH, payload=payload)
            results = response_payload.get('results') or []
            if results:
                return self._normalize_company_payload(results[0])
        return None

    def search_contact_by_email(self, *, email=''):
        if not email:
            return None
        payload = {
            'filterGroups': [{'filters': [{'propertyName': 'email', 'operator': 'EQ', 'value': email.lower()}]}],
            'properties': ['firstname', 'lastname', 'email', 'phone', 'company', 'website'],
            'limit': 1,
        }
        response_payload = self._request('POST', HUBSPOT_CONTACTS_SEARCH_PATH, payload=payload)
        results = response_payload.get('results') or []
        return self._normalize_contact_payload(results[0]) if results else None

    def _request(self, method, path, *, payload=None, query=None):
        url = f'{self.base_url}{path}'
        if query:
            url = f'{url}?{parse.urlencode(query, doseq=True)}'

        body = None
        headers = {
            'Authorization': f'Bearer {self._strip_bearer(self.api_key)}',
            'Accept': 'application/json',
        }
        if payload is not None:
            body = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'

        hubspot_request = request.Request(url, data=body, headers=headers, method=method.upper())

        try:
            with request.urlopen(hubspot_request, timeout=self.timeout) as hubspot_response:
                raw_response = hubspot_response.read().decode('utf-8')
                return json.loads(raw_response) if raw_response else {}
        except error.HTTPError as exc:
            raw_error = exc.read().decode('utf-8')
            raise HubSpotApiError(f'HubSpot erro {exc.code} em {path}. body={raw_error[:1000]}') from exc
        except error.URLError as exc:
            raise HubSpotApiError('HubSpot está indisponível no momento. Tente novamente.') from exc

    @staticmethod
    def _strip_bearer(value):
        token = (value or '').strip()
        return token[7:].strip() if token.lower().startswith('bearer ') else token

    @staticmethod
    def extract_domain_from_website(website):
        cleaned_website = (website or '').strip().lower()
        if not cleaned_website:
            return ''
        parsed_url = parse.urlparse(cleaned_website if '://' in cleaned_website else f'https://{cleaned_website}')
        host = (parsed_url.netloc or parsed_url.path).strip()
        return host[4:] if host.startswith('www.') else host

    @staticmethod
    def _normalize_company_payload(payload):
        properties = payload.get('properties') or {}
        return {
            'hubspot_company_id': str(payload.get('id') or ''),
            'name': properties.get('name') or 'Empresa sem nome',
            'website': properties.get('website') or '',
            'phone': properties.get('phone') or '',
            'raw_payload': payload,
        }

    @staticmethod
    def _normalize_contact_payload(payload):
        properties = payload.get('properties') or {}
        return {
            'hubspot_contact_id': str(payload.get('id') or ''),
            'first_name': properties.get('firstname') or '',
            'last_name': properties.get('lastname') or '',
            'email': properties.get('email') or '',
            'phone': properties.get('phone') or properties.get('mobilephone') or '',
            'company_name': properties.get('company') or '',
            'company_hubspot_id': '',
            'raw_payload': payload,
        }
