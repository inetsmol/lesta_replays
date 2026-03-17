from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from replays.models import SubscriptionPlan
from replays.services import SubscriptionService

User = get_user_model()


class SubscriptionServiceTests(TestCase):
    def test_get_user_plan_auto_downgrades_expired_subscription_to_free(self):
        user = User.objects.create_user(username="expired_sub_user", password="test-pass-123")
        subscription = user.subscription
        subscription.plan = SubscriptionPlan.objects.get(name=SubscriptionPlan.PLAN_PREMIUM)
        subscription.expires_at = timezone.now() - timedelta(days=1)
        subscription.expiry_reminder_sent_for_date = timezone.localdate() - timedelta(days=4)
        subscription.is_active = True
        subscription.save(update_fields=["plan", "expires_at", "expiry_reminder_sent_for_date", "is_active"])

        plan = SubscriptionService.get_user_plan(user)

        subscription.refresh_from_db()
        self.assertEqual(plan.name, SubscriptionPlan.PLAN_FREE)
        self.assertEqual(subscription.plan.name, SubscriptionPlan.PLAN_FREE)
        self.assertTrue(subscription.is_active)
        self.assertIsNone(subscription.expires_at)
        self.assertIsNone(subscription.expiry_reminder_sent_for_date)
