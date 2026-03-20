from io import BytesIO
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from accounts.models import User
from common.constants import ACTIVE_ORGANIZATION_SESSION_KEY
from companies.services import CompanyService
from imports.models import ImportJob
from imports.services import ImportPeopleService
from organizations.models import Organization, OrganizationMembership
from people.models import Person


class ImportAutoTriggerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='import-owner@example.com',
            full_name='Import Owner',
            password='StrongPass123!',
        )
        self.organization = Organization.objects.create(
            name='Imports Org',
            slug='imports-org',
            segment=Organization.Segment.TECHNOLOGY,
            team_size=Organization.TeamSize.SIZE_1_10,
            created_by=self.user,
        )
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.organization,
            role=OrganizationMembership.Role.OWNER,
            invited_by=self.user,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session[ACTIVE_ORGANIZATION_SESSION_KEY] = self.organization.id
        session.save()

    def _build_workbook_file(self, headers, row):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'modelo'
        sheet.append(headers)
        sheet.append(row)

        content = BytesIO()
        workbook.save(content)
        content.seek(0)
        content.name = 'import.xlsx'
        return content

    @patch('imports.views.ImportJobWorkerService.trigger_job_async')
    def test_people_import_triggers_worker_automatically(self, trigger_job_async_mock):
        upload_file = self._build_workbook_file(
            ['nome', 'sobrenome', 'email', 'telefone'],
            ['Ana', 'Silva', 'ana@example.com', '+55 11 91234-5678'],
        )

        response = self.client.post(
            reverse('imports:create_person_job'),
            {'file': upload_file},
        )

        self.assertEqual(response.status_code, 302)
        job = ImportJob.objects.get(entity_type=ImportJob.EntityType.PEOPLE)
        trigger_job_async_mock.assert_called_once_with(job_id=job.id)

    @patch('imports.views.ImportJobWorkerService.trigger_job_async')
    def test_company_import_triggers_worker_automatically(self, trigger_job_async_mock):
        upload_file = self._build_workbook_file(
            ['razao', 'cnpj', 'website', 'email', 'telefone'],
            ['ACME LTDA', '', 'https://acme.test', 'contato@acme.test', '+55 11 4000-0000'],
        )

        response = self.client.post(
            reverse('imports:create_company_job'),
            {'file': upload_file},
        )

        self.assertEqual(response.status_code, 302)
        job = ImportJob.objects.get(entity_type=ImportJob.EntityType.COMPANIES)
        trigger_job_async_mock.assert_called_once_with(job_id=job.id)


class ImportPeopleServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='import-people@example.com',
            full_name='Import People Owner',
            password='StrongPass123!',
        )
        self.organization = Organization.objects.create(
            name='Import People Org',
            slug='import-people-org',
            segment=Organization.Segment.TECHNOLOGY,
            team_size=Organization.TeamSize.SIZE_1_10,
            created_by=self.user,
        )
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.organization,
            role=OrganizationMembership.Role.OWNER,
            invited_by=self.user,
        )

    def test_import_people_links_company_by_razao_social(self):
        company = CompanyService.create_company(
            user=self.user,
            organization=self.organization,
            name='ACME LTDA',
            cnpj='12345678000199',
        )

        ImportPeopleService.import_payload(
            user=self.user,
            organization=self.organization,
            payload={
                'nome': 'Ana',
                'sobrenome': 'Silva',
                'telefone': '+55 11 91234-5678',
                'razao_empresa': 'acme ltda',
            },
        )

        person = Person.objects.get(organization=self.organization, first_name='Ana', last_name='Silva')
        self.assertEqual(person.company_id, company.id)

    def test_import_people_raises_error_when_razao_social_is_not_found(self):
        with self.assertRaisesMessage(ValidationError, 'Nenhuma empresa local encontrada para a razao Empresa Inexistente.'):
            ImportPeopleService.import_payload(
                user=self.user,
                organization=self.organization,
                payload={
                    'nome': 'Bruno',
                    'sobrenome': 'Souza',
                    'telefone': '+55 11 92222-3333',
                    'razao_empresa': 'Empresa Inexistente',
                },
            )

    def test_import_people_raises_error_when_razao_and_cnpj_conflict(self):
        CompanyService.create_company(
            user=self.user,
            organization=self.organization,
            name='ACME LTDA',
            cnpj='12345678000199',
        )
        CompanyService.create_company(
            user=self.user,
            organization=self.organization,
            name='Outra Empresa',
            cnpj='98765432000188',
        )

        with self.assertRaisesMessage(ValidationError, 'A razao da empresa e o CNPJ informado apontam para empresas diferentes.'):
            ImportPeopleService.import_payload(
                user=self.user,
                organization=self.organization,
                payload={
                    'nome': 'Carla',
                    'sobrenome': 'Lima',
                    'telefone': '+55 11 94444-5555',
                    'razao_empresa': 'ACME LTDA',
                    'cnpj_empresa': '98765432000188',
                },
            )
