import json

import requests
from apollo_integration.constants import (
    APOLLO_API_BASE_URL,
    APOLLO_DEFAULT_TIMEOUT_SECONDS,
    APOLLO_HTTP_USER_AGENT,
    APOLLO_MAX_RESULTS_PER_PAGE,
    APOLLO_ORGANIZATION_SEARCH_PATH,
    APOLLO_USAGE_STATS_PATH,
)
from apollo_integration.exceptions import ApolloApiError


class ApolloClient:
    def __init__(self, *, api_key, base_url=APOLLO_API_BASE_URL, timeout=APOLLO_DEFAULT_TIMEOUT_SECONDS):
        self.api_key = self._strip_bearer(api_key)
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()

    def search_organizations(self, *, payload):
        response_payload = self._request('POST', APOLLO_ORGANIZATION_SEARCH_PATH, payload=payload)
        organizations, source_key = self._extract_organization_items(response_payload)
        pagination = self._extract_pagination(response_payload)
        return {
            'organizations': [
                self._normalize_company_payload(item)
                for item in organizations
                if isinstance(item, dict)
            ],
            'pagination': pagination,
            'diagnostics': {
                'source_key': source_key,
                'recognized_count': len(organizations),
                'top_level_keys': list(response_payload.keys()) if isinstance(response_payload, dict) else [],
                'total_entries': pagination.get('total_entries') if isinstance(pagination, dict) else None,
            },
            'raw_payload': response_payload,
        }

    def search_companies(self, *, page=1, per_page=25):
        page = max(1, int(page or 1))
        per_page = max(1, min(int(per_page or 25), APOLLO_MAX_RESULTS_PER_PAGE))
        return self.search_organizations(payload={'page': page, 'per_page': per_page})

    def get_usage_stats(self):
        return self._request('POST', APOLLO_USAGE_STATS_PATH, payload={})

    def _request(self, method, path, *, payload=None, query=None):
        url = f'{self.base_url}{path}'
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Cache-Control': 'no-cache',
            'User-Agent': APOLLO_HTTP_USER_AGENT,
            'X-Api-Key': self.api_key,
        }

        try:
            apollo_response = self.session.request(
                method=method.upper(),
                url=url,
                headers=headers,
                params=query,
                json=payload if payload is not None else None,
                timeout=self.timeout,
            )
            apollo_response.raise_for_status()
            return apollo_response.json() if apollo_response.content else {}
        except requests.HTTPError as exc:
            response = exc.response
            raw_error = response.text if response is not None else ''
            error_message = self._build_http_error_message(path=path, status_code=response.status_code if response is not None else None, raw_error=raw_error)
            raise ApolloApiError(error_message) from exc
        except requests.RequestException as exc:
            raise ApolloApiError('Apollo esta indisponivel no momento. Tente novamente.') from exc

    @staticmethod
    def _build_http_error_message(*, path, status_code, raw_error):
        parsed_error = ApolloClient._parse_json(raw_error)
        if status_code == 403 and isinstance(parsed_error, dict) and parsed_error.get('error_code') == 1010:
            return (
                'Apollo bloqueou a assinatura HTTP desta requisicao (Cloudflare 1010). '
                'O Nephew CRM ja usa um User-Agent dedicado, mas se o bloqueio persistir '
                'sera necessario liberar este client com o suporte do Apollo. '
                f'body={raw_error[:1000]}'
            )
        return f'Apollo erro {status_code} em {path}. body={raw_error[:1000]}'

    @staticmethod
    def _parse_json(raw_value):
        try:
            return json.loads(raw_value) if raw_value else {}
        except (TypeError, ValueError):
            return {}

    @staticmethod
    def _extract_organization_items(response_payload):
        if isinstance(response_payload, list):
            return response_payload, 'root_list'
        if not isinstance(response_payload, dict):
            return [], None

        for key in ('organizations', 'accounts', 'companies', 'results'):
            value = response_payload.get(key)
            if isinstance(value, list):
                return value, key

        data = response_payload.get('data')
        if isinstance(data, dict):
            for key in ('organizations', 'accounts', 'companies', 'results'):
                value = data.get(key)
                if isinstance(value, list):
                    return value, f'data.{key}'
        elif isinstance(data, list):
            return data, 'data'

        return [], None

    @staticmethod
    def _extract_pagination(response_payload):
        if not isinstance(response_payload, dict):
            return {}
        pagination = response_payload.get('pagination')
        if isinstance(pagination, dict):
            return pagination
        data = response_payload.get('data')
        if isinstance(data, dict) and isinstance(data.get('pagination'), dict):
            return data['pagination']
        return {}

    @staticmethod
    def _strip_bearer(value):
        token = (value or '').strip()
        return token[7:].strip() if token.lower().startswith('bearer ') else token

    @staticmethod
    def _resolve_industries_label(industries):
        if not industries:
            return ''
        if isinstance(industries, list):
            names = []
            for item in industries:
                if isinstance(item, dict):
                    name = item.get('name') or item.get('label') or item.get('value')
                    if name:
                        names.append(name)
                elif item:
                    names.append(str(item))
            return ', '.join(names)
        if isinstance(industries, dict):
            return industries.get('name') or industries.get('label') or industries.get('value') or ''
        return str(industries)

    @staticmethod
    def _normalize_company_payload(payload):
        source = payload.get('organization') if isinstance(payload.get('organization'), dict) else payload
        industries = source.get('industries')
        industry = source.get('industry')
        segment = industry or ApolloClient._resolve_industries_label(industries)
        employee_count = (
            source.get('estimated_num_employees')
            or source.get('num_employees')
            or source.get('employee_count')
            or source.get('organization_num_employees')
        )

        try:
            employee_count = int(employee_count) if employee_count not in (None, '') else None
        except (TypeError, ValueError):
            employee_count = None

        return {
            'apollo_company_id': str(
                source.get('id')
                or payload.get('id')
                or source.get('organization_id')
                or ''
            ),
            'name': source.get('name') or payload.get('name') or 'Empresa sem nome',
            'website': source.get('website_url') or source.get('website') or '',
            'linkedin_url': source.get('linkedin_url') or '',
            'email': source.get('primary_email') or source.get('email') or '',
            'phone': source.get('primary_phone') or source.get('phone') or '',
            'segment': segment or '',
            'employee_count': employee_count,
            'raw_payload': payload,
        }


ApolloApiGateway = ApolloClient
