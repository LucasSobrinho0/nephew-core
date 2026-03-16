from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from organizations.models import Organization
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
