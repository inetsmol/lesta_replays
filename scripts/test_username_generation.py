"""
Тест логики генерации username из email.
"""
import os
import sys
import django

# Настройка Django окружения
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lesta_replays.settings')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()


def test_username_generation():
    """Тестирует логику генерации username."""

    test_cases = [
        "test@gmail.com",
        "user123@mail.ru",
        "another.user@yandex.ru",
        "kko080689@gmail.com",
        "lebedev-dm@mail.ru",
    ]

    print("Тест генерации username из email:")
    print("=" * 80)

    for email in test_cases:
        # Извлекаем базовое имя
        base_username = email.split('@')[0]

        # Проверяем уникальность
        if User.objects.filter(username=base_username).exists():
            # Генерируем уникальный username
            counter = 1
            new_username = f"{base_username}{counter}"
            while User.objects.filter(username=new_username).exists():
                counter += 1
                new_username = f"{base_username}{counter}"

            print(f"Email: {email:30s} → Username: {new_username:20s} (base '{base_username}' занят)")
        else:
            print(f"Email: {email:30s} → Username: {base_username:20s} ✅")

    print("\n" + "=" * 80)
    print("Проверка завершена!")


if __name__ == '__main__':
    test_username_generation()
