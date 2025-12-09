"""
Скрипт для исправления username пользователей, у которых используется полный email.
Заменяет полный email на часть до @.
"""
import os
import sys
import django

# Настройка Django окружения
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lesta_replays.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.db import transaction

User = get_user_model()

def fix_email_usernames(dry_run=True):
    """
    Исправляет username для пользователей, у которых используется полный email.

    Args:
        dry_run: Если True, только показывает что будет изменено, не сохраняет.
    """
    # Находим пользователей с @ в username
    users_with_email_username = User.objects.filter(username__contains='@').order_by('id')

    print(f"Найдено пользователей с @ в username: {users_with_email_username.count()}\n")

    if users_with_email_username.count() == 0:
        print("Нет пользователей для исправления.")
        return

    changes = []
    used_usernames = set()  # Отслеживаем уже использованные username в текущей сессии

    for user in users_with_email_username:
        # Извлекаем часть до @
        if '@' in user.username:
            base_username = user.username.split('@')[0]
            new_username = base_username

            # Проверяем, не занят ли уже такой username (в БД или в текущей сессии)
            if (User.objects.filter(username=new_username).exclude(pk=user.pk).exists() or
                new_username in used_usernames):
                # Если занят, добавляем суффикс с ID пользователя
                new_username = f"{base_username}_{user.id}"
                print(f"⚠️  Username '{base_username}' уже занят, используем '{new_username}'")

            used_usernames.add(new_username)

            changes.append({
                'user': user,
                'old_username': user.username,
                'new_username': new_username,
                'email': user.email
            })

    # Показываем планируемые изменения
    print("Планируемые изменения:")
    print("-" * 80)
    for change in changes:
        print(f"ID: {change['user'].id}")
        print(f"  Старый username: {change['old_username']}")
        print(f"  Новый username:  {change['new_username']}")
        print(f"  Email:           {change['email']}")
        print()

    if dry_run:
        print("\n⚠️  Это пробный запуск (dry run). Изменения НЕ сохранены.")
        print("Для применения изменений запустите скрипт с параметром --apply")
        return changes

    # Применяем изменения
    print("\n" + "=" * 80)
    print("Применение изменений...")
    print("=" * 80 + "\n")

    with transaction.atomic():
        for change in changes:
            user = change['user']
            old_username = user.username
            new_username = change['new_username']

            user.username = new_username
            user.save(update_fields=['username'])

            print(f"✅ Обновлен пользователь ID {user.id}: '{old_username}' → '{new_username}'")

    print(f"\n✅ Успешно обновлено {len(changes)} пользователей.")
    return changes


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Исправление username пользователей с email')
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Применить изменения (по умолчанию только показывается что будет изменено)'
    )

    args = parser.parse_args()

    fix_email_usernames(dry_run=not args.apply)
