from django.contrib.auth import authenticate
from django.db import connection
from django.test import TestCase

from accounts.models import User
from common.encryption import ENCRYPTED_VALUE_PREFIX, build_email_lookup


class UserSecurityTests(TestCase):
    def test_same_password_generates_different_hashes(self):
        first_user = User.objects.create_user(
            email='first@example.com',
            full_name='First User',
            password='StrongPass123!',
        )
        second_user = User.objects.create_user(
            email='second@example.com',
            full_name='Second User',
            password='StrongPass123!',
        )

        self.assertNotEqual(first_user.password, second_user.password)
        self.assertTrue(first_user.check_password('StrongPass123!'))
        self.assertTrue(second_user.check_password('StrongPass123!'))

    def test_email_is_encrypted_at_rest_and_lookup_is_hashed(self):
        user = User.objects.create_user(
            email='encrypted@example.com',
            full_name='Encrypted User',
            password='StrongPass123!',
        )

        with connection.cursor() as cursor:
            cursor.execute('SELECT email, email_lookup, username FROM accounts_user WHERE id = %s', [user.id])
            encrypted_email, email_lookup, username = cursor.fetchone()

        self.assertNotEqual(encrypted_email, 'encrypted@example.com')
        self.assertTrue(encrypted_email.startswith(ENCRYPTED_VALUE_PREFIX))
        self.assertEqual(email_lookup, build_email_lookup('encrypted@example.com'))
        self.assertEqual(username, email_lookup)
        self.assertEqual(User.objects.get(pk=user.pk).email, 'encrypted@example.com')

    def test_authentication_by_email_still_works_with_encrypted_storage(self):
        user = User.objects.create_user(
            email='login@example.com',
            full_name='Login User',
            password='StrongPass123!',
        )

        authenticated_user = authenticate(email='login@example.com', password='StrongPass123!')

        self.assertIsNotNone(authenticated_user)
        self.assertEqual(authenticated_user.pk, user.pk)
