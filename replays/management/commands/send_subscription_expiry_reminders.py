from django.core.management.base import BaseCommand

from replays.services import SubscriptionReminderService


class Command(BaseCommand):
    help = "Отправляет одноразовые email-напоминания за несколько дней до истечения подписки"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days-before",
            type=int,
            default=3,
            help="За сколько дней до истечения отправлять письмо (по умолчанию: 3)",
        )

    def handle(self, *args, **options):
        days_before = options["days_before"]
        subscriptions = list(SubscriptionReminderService.get_due_subscriptions(days_before=days_before))

        if not subscriptions:
            self.stdout.write(self.style.WARNING("Нет подписок для отправки напоминаний."))
            return

        sent_count = 0
        failed_count = 0

        for subscription in subscriptions:
            try:
                result = SubscriptionReminderService.send_expiry_reminder(
                    subscription,
                    days_before=days_before,
                )
                if result:
                    sent_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Отправлено: {subscription.user.email} "
                            f"(план: {subscription.plan.get_name_display()}, истекает: {subscription.expires_at:%d.%m.%Y})"
                        )
                    )
            except Exception as exc:
                failed_count += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"Ошибка отправки для {subscription.user.email}: {exc}"
                    )
                )

        self.stdout.write("")
        self.stdout.write(f"Всего кандидатов: {len(subscriptions)}")
        self.stdout.write(self.style.SUCCESS(f"Успешно отправлено: {sent_count}"))
        if failed_count:
            self.stdout.write(self.style.ERROR(f"Ошибок: {failed_count}"))
