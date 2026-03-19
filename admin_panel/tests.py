from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from admin_panel.models import AdminAccessLog
from admin_panel.services import SYSTEM_ADMIN_GROUP_NAME


class AdminPanelTests(TestCase):
    def setUp(self):
        self.admin_group, _ = Group.objects.get_or_create(name=SYSTEM_ADMIN_GROUP_NAME)
        self.admin_user = User.objects.create_user(
            email='system-admin@example.com',
            full_name='System Admin',
            password='StrongPass123!',
        )
        self.admin_user.groups.add(self.admin_group)
        self.regular_user = User.objects.create_user(
            email='regular@example.com',
            full_name='Regular User',
            password='StrongPass123!',
        )

    def test_admin_panel_requires_admin_group(self):
        self.client.force_login(self.regular_user)

        response = self.client.get(reverse('admin_panel:index'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], reverse('dashboard:home'))

    def test_admin_panel_overview_is_available_for_admin_group(self):
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse('admin_panel:index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Painel Admin')
        self.assertContains(response, 'IPs de acesso')

    def test_login_and_logout_create_access_log_entries(self):
        self.client.post(
            reverse('accounts:login'),
            {
                'email': 'system-admin@example.com',
                'password': 'StrongPass123!',
            },
        )

        access_log = AdminAccessLog.objects.get(user=self.admin_user)
        self.assertEqual(access_log.logged_in_by, self.admin_user)
        self.assertIsNotNone(access_log.logged_in_at)

        self.client.post(reverse('accounts:logout'))

        access_log.refresh_from_db()
        self.assertEqual(access_log.logged_out_by, self.admin_user)
        self.assertIsNotNone(access_log.logged_out_at)

    def test_ip_log_list_supports_page_size_selection(self):
        for index in range(30):
            AdminAccessLog.objects.create(
                user=self.admin_user,
                logged_in_by=self.admin_user,
                session_key=f'session-{index}',
                ip_address=f'192.168.0.{(index % 10) + 1}',
            )

        self.client.force_login(self.admin_user)

        response = self.client.get(reverse('admin_panel:ip_logs'), {'per_page': 10})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['ip_logs']), 10)
        self.assertTrue(response.context['pagination']['next_url'])

    def test_ip_log_list_uses_cursor_navigation(self):
        for index in range(12):
            AdminAccessLog.objects.create(
                user=self.admin_user,
                logged_in_by=self.admin_user,
                session_key=f'cursor-session-{index}',
                ip_address=f'172.16.0.{index + 1}',
            )

        self.client.force_login(self.admin_user)

        first_response = self.client.get(reverse('admin_panel:ip_logs'), {'per_page': 5})

        self.assertEqual(first_response.status_code, 200)
        next_url = first_response.context['pagination']['next_url']
        self.assertIn('cursor=', next_url)
        self.assertIn('direction=next', next_url)

    def test_authenticated_session_without_login_event_is_logged_by_middleware(self):
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse('dashboard:home'), REMOTE_ADDR='10.0.0.1')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AdminAccessLog.objects.filter(
                user=self.admin_user,
                ip_address='10.0.0.1',
            ).exists()
        )

    def test_ip_change_creates_new_access_log_for_same_session(self):
        self.client.force_login(self.admin_user)

        self.client.get(reverse('dashboard:home'), REMOTE_ADDR='10.0.0.1')
        first_log = AdminAccessLog.objects.filter(user=self.admin_user).latest('logged_in_at', 'id')

        self.client.get(reverse('dashboard:home'), REMOTE_ADDR='10.0.0.2')

        first_log.refresh_from_db()
        latest_log = AdminAccessLog.objects.filter(user=self.admin_user).latest('logged_in_at', 'id')
        self.assertIsNotNone(first_log.logged_out_at)
        self.assertEqual(first_log.logged_out_by, self.admin_user)
        self.assertEqual(latest_log.ip_address, '10.0.0.2')
        self.assertIsNone(latest_log.logged_out_at)
