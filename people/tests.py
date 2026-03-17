from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from common.constants import ACTIVE_ORGANIZATION_SESSION_KEY
from organizations.models import Organization, OrganizationMembership
from people.models import Person
from people.repositories import PersonRepository
from people.services import PersonService


class PersonSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='person-owner@example.com',
            full_name='Person Owner',
            password='StrongPass123!',
        )
        self.organization = Organization.objects.create(
            name='People Org',
            slug='people-org',
            segment=Organization.Segment.TECHNOLOGY,
            team_size=Organization.TeamSize.SIZE_1_10,
            created_by=self.user,
        )
        self.other_organization = Organization.objects.create(
            name='Other Org',
            slug='other-org',
            segment=Organization.Segment.SERVICES,
            team_size=Organization.TeamSize.SIZE_1_10,
            created_by=self.user,
        )
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.organization,
            role=OrganizationMembership.Role.OWNER,
            invited_by=self.user,
        )

    def test_phone_is_unique_per_organization_after_normalization(self):
        PersonService.create_person(
            user=self.user,
            organization=self.organization,
            first_name='Ana',
            last_name='Costa',
            phone='(11) 91234-5678',
        )

        with self.assertRaises(ValidationError):
            PersonService.create_person(
                user=self.user,
                organization=self.organization,
                first_name='Ana',
                last_name='Costa Duplicate',
                phone='+55 11 91234-5678',
            )

        person = PersonService.create_person(
            user=self.user,
            organization=self.other_organization,
            first_name='Ana',
            last_name='Costa Other',
            phone='+55 11 91234-5678',
        )

        self.assertEqual(person.normalized_phone, '5511912345678')

    def test_bot_conversa_id_is_unique_per_organization(self):
        PersonService.create_person(
            user=self.user,
            organization=self.organization,
            first_name='Bruno',
            last_name='Lima',
            phone='+55 11 94444-0000',
            bot_conversa_id='subscriber-123',
        )

        with self.assertRaises(ValidationError):
            PersonService.create_person(
                user=self.user,
                organization=self.organization,
                first_name='Bruna',
                last_name='Lima',
                phone='+55 11 95555-0000',
                bot_conversa_id='subscriber-123',
            )

    def test_email_is_unique_per_organization_after_normalization(self):
        PersonService.create_person(
            user=self.user,
            organization=self.organization,
            first_name='Carla',
            last_name='Souza',
            email='Carla@Empresa.com',
            phone='+55 11 93333-0000',
        )

        with self.assertRaises(ValidationError):
            PersonService.create_person(
                user=self.user,
                organization=self.organization,
                first_name='Carla',
                last_name='Duplicada',
                email='carla@empresa.com',
                phone='+55 11 94444-9999',
            )

    def test_update_person_rejects_cross_tenant_person(self):
        person = PersonService.create_person(
            user=self.user,
            organization=self.other_organization,
            first_name='Diego',
            last_name='Oliveira',
            email='diego@example.com',
            phone='+55 11 91111-1111',
        )

        with self.assertRaises(ValidationError):
            PersonService.update_person(
                user=self.user,
                organization=self.organization,
                person=person,
                first_name='Diego',
                last_name='Alterado',
                email='diego2@example.com',
                phone='+55 11 91111-1111',
            )

    def test_people_page_lists_only_active_organization_people(self):
        self.client.force_login(self.user)
        session = self.client.session
        session[ACTIVE_ORGANIZATION_SESSION_KEY] = self.organization.id
        session.save()

        own_person = PersonService.create_person(
            user=self.user,
            organization=self.organization,
            first_name='Eva',
            last_name='Costa',
            email='eva@example.com',
            phone='+55 11 92222-1111',
        )
        PersonService.create_person(
            user=self.user,
            organization=self.other_organization,
            first_name='Filipe',
            last_name='Paz',
            email='filipe@example.com',
            phone='+55 11 92222-2222',
        )

        response = self.client.get(reverse('people:index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own_person.full_name)
        self.assertNotContains(response, 'Filipe Paz')

    def test_people_update_view_updates_email_and_phone(self):
        self.client.force_login(self.user)
        session = self.client.session
        session[ACTIVE_ORGANIZATION_SESSION_KEY] = self.organization.id
        session.save()

        person = PersonService.create_person(
            user=self.user,
            organization=self.organization,
            first_name='Giovana',
            last_name='Moraes',
            email='giovana@example.com',
            phone='+55 11 97777-1111',
        )

        response = self.client.post(
            reverse('people:edit', kwargs={'person_public_id': person.public_id}),
            {
                'first_name': 'Giovana',
                'last_name': 'Moraes Silva',
                'email': 'giovana.silva@example.com',
                'phone': '+55 11 97777-2222',
            },
        )

        self.assertEqual(response.status_code, 302)
        person = PersonRepository.get_for_organization_and_public_id(self.organization, person.public_id)
        self.assertEqual(person.email, 'giovana.silva@example.com')
        self.assertEqual(person.normalized_phone, '5511977772222')
