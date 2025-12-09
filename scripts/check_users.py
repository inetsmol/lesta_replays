"""
Проверка текущего состояния пользователей.
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

# Находим пользователей с @ в username
users_with_email = User.objects.filter(username__contains='@').order_by('id')

print(f"Пользователи с @ в username ({users_with_email.count()}):\n")
for user in users_with_email:
    print(f"ID: {user.id:4d} | username: {user.username:30s} | email: {user.email or 'нет email'}")

# Проверяем дубликаты username
from django.db.models import Count

duplicates = (User.objects
              .values('username')
              .annotate(count=Count('id'))
              .filter(count__gt=1))

if duplicates:
    print(f"\n\nДубликаты username ({duplicates.count()}):")
    print("-" * 80)
    for dup in duplicates:
        users = User.objects.filter(username=dup['username']).order_by('id')
        print(f"\nUsername '{dup['username']}' ({dup['count']} пользователей):")
        for user in users:
            print(f"  ID: {user.id:4d} | email: {user.email or 'нет email'}")
else:
    print("\n\n✅ Дубликатов username не найдено.")
