from io import BytesIO
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from accounts.models import User
from common.constants import ACTIVE_ORGANIZATION_SESSION_KEY
from imports.models import ImportJob
from organizations.models import Organization, OrganizationMembership


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
