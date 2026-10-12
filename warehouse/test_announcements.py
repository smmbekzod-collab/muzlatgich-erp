import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse

from core.models import Organization
from .announcements import HEADER, deliver_one
from .models import TelegramAlertDestination, TelegramAnnouncement, TelegramAnnouncementDelivery


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
    STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
              'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class AnnouncementTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('announcer', password='test-pass-12345')
        self.staff = get_user_model().objects.create_user('staff', is_staff=True)
        self.org = Organization.objects.create(name='Tashkilot A', code='announce-a')
        self.other = Organization.objects.create(name='Tashkilot B', code='announce-b')
        self.route = TelegramAlertDestination.objects.create(organization=self.org,
            chat_id='-1001111', enabled=True, updated_by=self.admin)
        self.route2 = TelegramAlertDestination.objects.create(organization=self.other,
            chat_id='-1002222', enabled=True, updated_by=self.admin)
        self.url = reverse('telegram_announcements')
        self.client.force_login(self.admin)
        self.token = patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': '123:test-token'})
        self.token.start()
        self.addCleanup(self.token.stop)

    def preview(self, routes=None, body='Yangi imkoniyat <script>alert(1)</script>'):
        return self.client.post(self.url, {'body': body, 'destinations': routes or [self.route.pk]})

    def confirmed(self, routes=None):
        response = self.preview(routes)
        self.client.post(self.url, {'action': 'confirm', 'preview': response.context['preview']})
        return TelegramAnnouncement.objects.get()

    def test_preview_is_escaped_and_does_not_send_or_create(self):
        with patch('warehouse.announcements.send_message') as send:
            response = self.preview()
        self.assertContains(response, '&lt;script&gt;')
        self.assertContains(response, self.route.chat_id)
        self.assertNotContains(response, self.route2.chat_id)
        self.assertFalse(TelegramAnnouncement.objects.exists())
        send.assert_not_called()


    def test_permissions_on_all_endpoints(self):
        item = self.confirmed()
        for user in [self.staff, None]:
            if user: self.client.force_login(user)
            else: self.client.logout()
            expected = 403 if user else 302
            self.assertEqual(self.client.get(self.url).status_code, expected)
            self.assertEqual(self.client.get(reverse('telegram_announcement', args=[item.pk])).status_code, expected)
            self.assertEqual(self.client.post(reverse('telegram_announcement_send', args=[item.pk])).status_code, expected)

    def test_csrf_and_get_cannot_send(self):
        item = self.confirmed()
        url = reverse('telegram_announcement_send', args=[item.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(url).status_code, 403)
        self.assertEqual(client.post(self.url, {'body': 'news'}).status_code, 403)

    def test_confirmation_replay_creates_one_announcement(self):
        preview = self.preview().context['preview']
        for _ in range(2):
            self.assertEqual(self.client.post(self.url, {'action': 'confirm', 'preview': preview}).status_code, 302)
        self.assertEqual(TelegramAnnouncement.objects.count(), 1)
        self.assertEqual(TelegramAnnouncementDelivery.objects.count(), 1)

    def test_modified_preview_and_cross_user_rejected(self):
        preview = self.preview().context['preview']
        self.client.post(self.url, {'action': 'confirm', 'preview': preview + 'x'})
        other_admin = get_user_model().objects.create_superuser('otheradmin', password='test-pass-12345')
        self.client.force_login(other_admin)
        self.client.post(self.url, {'action': 'confirm', 'preview': preview})
        self.assertFalse(TelegramAnnouncement.objects.exists())

    def test_changed_route_requires_new_preview(self):
        preview = self.preview().context['preview']
        self.route.chat_id = '-1003333'
        self.route.save()
        self.client.post(self.url, {'action': 'confirm', 'preview': preview})
        self.assertFalse(TelegramAnnouncement.objects.exists())

    def test_selected_groups_only_and_duplicate_send_is_noop(self):
        item = self.confirmed()
        url = reverse('telegram_announcement_send', args=[item.pk])
        with patch('warehouse.announcements.send_message') as send:
            for _ in range(2):
                self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        send.assert_called_once_with('123:test-token', self.route.chat_id, HEADER + item.body)
        delivery = item.deliveries.get()
        self.assertEqual(delivery.status, 'sent')
        self.assertIsNotNone(delivery.sent_at)
        self.assertEqual(item.deliveries.count(), 1)

    def test_multiple_groups_bounded_one_per_request_and_history(self):
        item = self.confirmed([self.route.pk, self.route2.pk])
        url = reverse('telegram_announcement_send', args=[item.pk])
        with patch('warehouse.announcements.send_message') as send:
            response = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            self.assertEqual(response.json()['remaining'], 1)
            self.assertEqual(send.call_count, 1)
            self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(send.call_count, 2)
        self.assertContains(self.client.get(self.url), 'Tashkilot B: Yuborildi')

    def test_disabled_or_inactive_groups_cannot_be_selected(self):
        self.route.enabled = False
        self.route.save()
        self.other.is_active = False
        self.other.save()
        response = self.preview([self.route.pk, self.route2.pk])
        self.assertTrue(response.context['form'].errors)
        self.assertFalse(TelegramAnnouncement.objects.exists())

    def test_route_changed_after_confirmation_is_not_sent(self):
        item = self.confirmed()
        self.route.chat_id = '-1009999'
        self.route.save()
        with patch('warehouse.announcements.send_message') as send:
            self.assertEqual(deliver_one(item.deliveries.get().pk), 'cancelled')
        send.assert_not_called()

    def test_uncertain_delivery_not_retried_and_secret_not_saved(self):
        item = self.confirmed()
        delivery = item.deliveries.get()
        with patch('warehouse.announcements.send_message', side_effect=RuntimeError('123:test-token')) as send:
            self.assertEqual(deliver_one(delivery.pk), 'failed')
            self.assertEqual(deliver_one(delivery.pk), 'failed')
        send.assert_called_once()
        delivery.refresh_from_db()
        self.assertNotIn('test-token', delivery.last_error)

    def test_length_empty_recipients_and_missing_token(self):
        self.assertTrue(self.preview(body='😀' * 2500).context['form'].errors)
        response = self.client.post(self.url, {'body': 'news'})
        self.assertTrue(response.context['form'].errors)
        item = self.confirmed()
        with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': ''}), patch('warehouse.announcements.send_message') as send:
            self.assertEqual(deliver_one(item.deliveries.get().pk), 'failed')
        send.assert_not_called()


@skipUnlessDBFeature('has_select_for_update')
class ConcurrentAnnouncementTests(TransactionTestCase):
    def test_two_requests_claim_one_delivery(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from django.db import close_old_connections
        admin = get_user_model().objects.create_superuser('parallel-announcer', password='test-pass-12345')
        org = Organization.objects.create(name='Parallel test', code='parallel-announcement')
        route = TelegramAlertDestination.objects.create(organization=org, chat_id='-1003333',
            enabled=True, updated_by=admin)
        item = TelegramAnnouncement.objects.create(body='Concurrent test', created_by=admin)
        delivery = TelegramAnnouncementDelivery.objects.create(announcement=item, destination=route,
            organization_name=org.name, chat_id=route.chat_id)
        entered, release = Event(), Event()

        def network(*args):
            entered.set()
            if not release.wait(10):
                raise TimeoutError()

        def run():
            close_old_connections()
            try:
                return deliver_one(delivery.pk)
            finally:
                close_old_connections()

        with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': '123:mock'}), \
             patch('warehouse.announcements.send_message', side_effect=network) as send, \
             ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(run)
            try:
                self.assertTrue(entered.wait(5))
                second = pool.submit(run)
                self.assertEqual(second.result(timeout=5), 'sending')
            finally:
                release.set()
            self.assertEqual(first.result(timeout=5), 'sent')
            self.assertEqual(send.call_count, 1)

