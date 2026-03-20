from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import authenticate
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from accounts.services import AccountService
from common.middleware import SessionTimeoutMiddleware
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


class AccountSessionTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            email='session@example.com',
            full_name='Session User',
            password='StrongPass123!',
        )

    def _build_request(self):
        request = self.factory.post('/login/')
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        return request

    def test_login_without_remember_me_expires_in_two_hours(self):
        request = self._build_request()

        AccountService.login_user(request, self.user, remember_me=False)

        self.assertEqual(request.session.get_expiry_age(), settings.NON_REMEMBERED_SESSION_AGE)
        self.assertIn(AccountService.FIXED_SESSION_DEADLINE_KEY, request.session)

    def test_login_with_remember_me_uses_default_persistent_session_age(self):
        request = self._build_request()

        AccountService.login_user(request, self.user, remember_me=True)

        self.assertEqual(request.session.get_expiry_age(), settings.SESSION_COOKIE_AGE)
        self.assertNotIn(AccountService.FIXED_SESSION_DEADLINE_KEY, request.session)

    def test_has_fixed_session_expired_returns_true_after_deadline(self):
        request = self._build_request()
        request.session[AccountService.FIXED_SESSION_DEADLINE_KEY] = (
            timezone.now() - timedelta(seconds=1)
        ).isoformat()

        self.assertTrue(AccountService.has_fixed_session_expired(request))

    def test_has_fixed_session_expired_returns_false_before_deadline(self):
        request = self._build_request()
        request.session[AccountService.FIXED_SESSION_DEADLINE_KEY] = (
            timezone.now() + timedelta(seconds=60)
        ).isoformat()

        self.assertFalse(AccountService.has_fixed_session_expired(request))


class SessionTimeoutMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            email='middleware@example.com',
            full_name='Middleware User',
            password='StrongPass123!',
        )

    def _build_request(self):
        request = self.factory.get('/dashboard/')
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        request.user = self.user
        return request

    def test_expired_fixed_session_logs_user_out_and_redirects_to_login(self):
        request = self._build_request()
        request.session[AccountService.FIXED_SESSION_DEADLINE_KEY] = (
            timezone.now() - timedelta(seconds=1)
        ).isoformat()
        middleware = SessionTimeoutMiddleware(lambda req: None)

        response = middleware(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('accounts:login'))
        self.assertIsInstance(request.user, AnonymousUser)

    def test_active_fixed_session_allows_request_through(self):
        request = self._build_request()
        request.session[AccountService.FIXED_SESSION_DEADLINE_KEY] = (
            timezone.now() + timedelta(seconds=60)
        ).isoformat()
        response = object()
        middleware = SessionTimeoutMiddleware(lambda req: response)

        returned_response = middleware(request)

        self.assertIs(returned_response, response)
