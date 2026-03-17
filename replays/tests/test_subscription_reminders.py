from datetime import timedelta
from io import StringIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from replays.models import SubscriptionPlan

User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SubscriptionReminderCommandTests(TestCase):
    def setUp(self):
        Site.objects.update_or_create(
            id=settings.SITE_ID,
            defaults={"domain": "lesta-replays.ru", "name": "Lesta Replays"},
        )

        self.premium_plan = SubscriptionPlan.objects.get(name=SubscriptionPlan.PLAN_PREMIUM)

    def _set_paid_subscription(self, user, *, expires_delta_days: int, reminder_sent_for_date=None):
        subscription = user.subscription
        subscription.plan = self.premium_plan
        subscription.expires_at = timezone.now() + timedelta(days=expires_delta_days)
        subscription.expiry_reminder_sent_for_date = reminder_sent_for_date
        subscription.is_active = True
        subscription.save(
            update_fields=[
                "plan",
                "expires_at",
                "expiry_reminder_sent_for_date",
                "is_active",
            ]
        )
        return subscription

    def test_command_sends_single_reminder_for_subscription_expiring_in_three_days(self):
        user = User.objects.create_user(
            username="expiring_user",
            email="expiring@example.com",
            password="test-pass-123",
        )
        subscription = self._set_paid_subscription(user, expires_delta_days=3)

        stdout = StringIO()
        call_command("send_subscription_expiry_reminders", stdout=stdout)

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["expiring@example.com"])
        self.assertIn("истекает через 3 дня", email.subject)
        self.assertIn("https://lesta-replays.ru/subscription/", email.body)

        subscription.refresh_from_db()
        self.assertEqual(subscription.expiry_reminder_sent_for_date, subscription.expires_at.date())

    def test_command_does_not_resend_same_reminder_on_second_run(self):
        user = User.objects.create_user(
            username="expiring_user_repeat",
            email="expiring-repeat@example.com",
            password="test-pass-123",
        )
        subscription = self._set_paid_subscription(user, expires_delta_days=3)

        call_command("send_subscription_expiry_reminders")
        call_command("send_subscription_expiry_reminders")

        self.assertEqual(len(mail.outbox), 1)
        subscription.refresh_from_db()
        self.assertEqual(subscription.expiry_reminder_sent_for_date, subscription.expires_at.date())

    def test_command_skips_free_without_email_and_wrong_date(self):
        eligible_user = User.objects.create_user(
            username="eligible_user",
            email="eligible@example.com",
            password="test-pass-123",
        )
        self._set_paid_subscription(eligible_user, expires_delta_days=3)

        no_email_user = User.objects.create_user(
            username="no_email_user",
            email="",
            password="test-pass-123",
        )
        self._set_paid_subscription(no_email_user, expires_delta_days=3)

        wrong_date_user = User.objects.create_user(
            username="wrong_date_user",
            email="wrong-date@example.com",
            password="test-pass-123",
        )
        self._set_paid_subscription(wrong_date_user, expires_delta_days=2)

        free_user = User.objects.create_user(
            username="free_user",
            email="free@example.com",
            password="test-pass-123",
        )

        call_command("send_subscription_expiry_reminders")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["eligible@example.com"])
        self.assertEqual(free_user.subscription.plan.name, SubscriptionPlan.PLAN_FREE)
