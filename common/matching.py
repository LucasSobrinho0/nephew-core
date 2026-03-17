import unicodedata
from urllib.parse import urlparse

from common.encryption import build_email_lookup, normalize_email_address
from common.phone import normalize_phone


def normalize_text(value):
    text = (value or '').strip().lower()
    if not text:
        return ''
    normalized = unicodedata.normalize('NFD', text)
    return ''.join(char for char in normalized if unicodedata.category(char) != 'Mn')


def normalize_full_name(*, first_name='', last_name='', full_name=''):
    raw_full_name = full_name or f'{first_name} {last_name}'
    return normalize_text(raw_full_name)


def normalize_company_domain(*, website='', domain=''):
    resolved_domain = (domain or '').strip().lower()
    if resolved_domain:
        return resolved_domain
    cleaned_website = (website or '').strip().lower()
    if not cleaned_website:
        return ''
    parsed_url = urlparse(cleaned_website if '://' in cleaned_website else f'https://{cleaned_website}')
    host = (parsed_url.netloc or parsed_url.path).strip()
    return host[4:] if host.startswith('www.') else host


def build_company_indexes(*, companies):
    companies_by_hubspot_id = {}
    companies_by_domain = {}
    companies_by_phone = {}
    companies_by_name = {}

    for company in companies:
        if company.hubspot_company_id:
            companies_by_hubspot_id[company.hubspot_company_id] = company
        if company.website:
            companies_by_domain[normalize_company_domain(website=company.website)] = company
        if company.normalized_phone:
            companies_by_phone[company.normalized_phone] = company
        companies_by_name[normalize_text(company.name)] = company

    return {
        'by_hubspot_id': companies_by_hubspot_id,
        'by_domain': companies_by_domain,
        'by_phone': companies_by_phone,
        'by_name': companies_by_name,
    }


def build_person_indexes(*, persons):
    persons_by_hubspot_id = {}
    persons_by_bot_conversa_id = {}
    persons_by_email_lookup = {}
    persons_by_phone = {}
    persons_by_name_email = {}
    persons_by_name_phone = {}
    persons_by_name = {}

    for person in persons:
        if person.hubspot_contact_id:
            persons_by_hubspot_id[person.hubspot_contact_id] = person
        if person.bot_conversa_id:
            persons_by_bot_conversa_id[person.bot_conversa_id] = person
        if person.email_lookup:
            persons_by_email_lookup[person.email_lookup] = person
        if person.normalized_phone:
            persons_by_phone[person.normalized_phone] = person

        normalized_name = normalize_full_name(first_name=person.first_name, last_name=person.last_name)
        if normalized_name:
            persons_by_name[normalized_name] = person
            if person.email_lookup:
                persons_by_name_email[(normalized_name, person.email_lookup)] = person
            if person.normalized_phone:
                persons_by_name_phone[(normalized_name, person.normalized_phone)] = person

    return {
        'by_hubspot_id': persons_by_hubspot_id,
        'by_bot_conversa_id': persons_by_bot_conversa_id,
        'by_email_lookup': persons_by_email_lookup,
        'by_phone': persons_by_phone,
        'by_name_email': persons_by_name_email,
        'by_name_phone': persons_by_name_phone,
        'by_name': persons_by_name,
    }


def match_company(*, remote_company, company_indexes):
    remote_hubspot_id = (remote_company.get('hubspot_company_id') or '').strip()
    remote_domain = normalize_company_domain(
        website=remote_company.get('website', ''),
        domain=remote_company.get('domain', ''),
    )
    remote_phone = ''
    if remote_company.get('phone'):
        try:
            remote_phone = normalize_phone(remote_company.get('phone'))
        except Exception:
            remote_phone = ''
    remote_name = normalize_text(remote_company.get('name'))

    return (
        company_indexes['by_hubspot_id'].get(remote_hubspot_id)
        or company_indexes['by_domain'].get(remote_domain)
        or company_indexes['by_phone'].get(remote_phone)
        or company_indexes['by_name'].get(remote_name)
    )


def match_person(*, remote_contact, person_indexes, integration_key='hubspot'):
    remote_id = (
        (remote_contact.get('hubspot_contact_id') or '').strip()
        if integration_key == 'hubspot'
        else (remote_contact.get('external_subscriber_id') or '').strip()
    )
    remote_email = normalize_email_address(remote_contact.get('email', '')) if remote_contact.get('email') else ''
    remote_email_lookup = build_email_lookup(remote_email) if remote_email else ''
    remote_phone = ''
    if remote_contact.get('phone'):
        try:
            remote_phone = normalize_phone(remote_contact.get('phone'))
        except Exception:
            remote_phone = ''
    remote_name = normalize_full_name(
        first_name=remote_contact.get('first_name', ''),
        last_name=remote_contact.get('last_name', ''),
        full_name=remote_contact.get('name', ''),
    )

    if integration_key == 'hubspot' and remote_id:
        person = person_indexes['by_hubspot_id'].get(remote_id)
        if person is not None:
            return person
    if integration_key == 'bot_conversa' and remote_id:
        person = person_indexes['by_bot_conversa_id'].get(remote_id)
        if person is not None:
            return person

    if remote_email_lookup:
        person = person_indexes['by_email_lookup'].get(remote_email_lookup)
        if person is not None:
            return person
    if remote_phone:
        person = person_indexes['by_phone'].get(remote_phone)
        if person is not None:
            return person
    if remote_name and remote_email_lookup:
        person = person_indexes['by_name_email'].get((remote_name, remote_email_lookup))
        if person is not None:
            return person
    if remote_name and remote_phone:
        person = person_indexes['by_name_phone'].get((remote_name, remote_phone))
        if person is not None:
            return person
    return person_indexes['by_name'].get(remote_name)
