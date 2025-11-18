# replays/management/commands/create_user_profiles.py
"""Management command для создания UserProfile для существующих пользователей."""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from allauth.socialaccount.models import SocialAccount
from replays.models import UserProfile

User = get_user_model()


class Command(BaseCommand):
    """
    Создать UserProfile для всех существующих пользователей.

    Если у пользователя есть Lesta аккаунт, автоматически заполняет lesta_account_id.
    """

    help = 'Создать UserProfile для всех существующих пользователей'

    def add_arguments(self, parser):
        parser.add_argument(
            '--update',
            action='store_true',
            help='Обновить lesta_account_id для существующих профилей',
        )

    def handle(self, *args, **options):
        """
        Выполнить команду.

        Args:
            *args: Позиционные аргументы
            **options: Именованные аргументы
        """
        update_existing = options['update']

        created_count = 0
        updated_count = 0
        skipped_count = 0

        users = User.objects.all()
        total_users = users.count()

        self.stdout.write(f'Найдено пользователей: {total_users}\n')

        for user in users:
            # Проверяем, есть ли уже профиль
            profile, created = UserProfile.objects.get_or_create(user=user)

            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Создан профиль для {user.username}')
                )
            elif not update_existing:
                skipped_count += 1
                continue

            # Получаем Lesta аккаунт если есть
            social_account = SocialAccount.objects.filter(
                user=user,
                provider='lesta'
            ).first()

            if social_account:
                account_id = social_account.uid

                # Обновляем только если значение изменилось
                if profile.lesta_account_id != account_id:
                    profile.lesta_account_id = account_id
                    profile.save(update_fields=['lesta_account_id', 'updated_at'])

                    if created:
                        self.stdout.write(
                            f'  → lesta_account_id: {account_id}'
                        )
                    else:
                        updated_count += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f'⟳ Обновлён {user.username}: lesta_account_id={account_id}'
                            )
                        )

        # Итоговая статистика
        self.stdout.write('\n' + '=' * 50)
        self.stdout.write(self.style.SUCCESS(f'\n✓ Создано профилей: {created_count}'))

        if update_existing:
            self.stdout.write(self.style.WARNING(f'⟳ Обновлено профилей: {updated_count}'))
            self.stdout.write(f'- Пропущено (без изменений): {total_users - created_count - updated_count}')
        else:
            self.stdout.write(f'- Пропущено (уже есть): {skipped_count}')
            if skipped_count > 0:
                self.stdout.write(
                    self.style.NOTICE(
                        '\nИспользуйте --update для обновления существующих профилей'
                    )
                )

        self.stdout.write('')
