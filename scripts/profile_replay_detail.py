#!/usr/bin/env python
"""
Скрипт для профилирования обработки страницы деталей реплея.

Использование:
    python scripts/profile_replay_detail.py <replay_id>

Пример:
    python scripts/profile_replay_detail.py 1
"""

import os
import sys
import django
import cProfile
import pstats
import io
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Настраиваем Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lesta_replays.settings')
django.setup()

from django.test import RequestFactory
from replays.views import ReplayDetailView
from replays.models import Replay


def profile_replay_detail(replay_id: int, runs: int = 3):
    """
    Профилирует обработку страницы деталей реплея.

    Args:
        replay_id: ID реплея для профилирования
        runs: Количество запусков для усреднения результатов
    """
    try:
        replay = Replay.objects.select_related('tank', 'owner', 'user', 'map').get(pk=replay_id)
    except Replay.DoesNotExist:
        print(f"❌ Реплей с ID {replay_id} не найден")
        return

    print(f"📊 Профилирование реплея ID={replay_id}")
    print(f"   Танк: {replay.tank.name if replay.tank else 'N/A'}")
    print(f"   Игрок: {replay.owner.real_name if replay.owner else 'N/A'}")
    print(f"   Дата боя: {replay.battle_date}")
    print(f"   Запусков: {runs}\n")

    factory = RequestFactory()

    # Профилируем get_context_data
    pr = cProfile.Profile()

    for i in range(runs):
        request = factory.get(f'/replays/{replay_id}/')
        view = ReplayDetailView()
        view.request = request
        view.object = replay

        pr.enable()
        try:
            context = view.get_context_data()
        except Exception as e:
            pr.disable()
            print(f"❌ Ошибка при профилировании: {e}")
            return
        pr.disable()

    # Выводим статистику
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s)
    ps.strip_dirs()
    ps.sort_stats('cumulative')

    print("=" * 80)
    print("📈 ТОП-30 ФУНКЦИЙ ПО CUMULATIVE TIME")
    print("=" * 80)
    ps.print_stats(30)
    print(s.getvalue())

    # Статистика по времени
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s)
    ps.strip_dirs()
    ps.sort_stats('time')

    print("\n" + "=" * 80)
    print("📈 ТОП-30 ФУНКЦИЙ ПО TOTAL TIME")
    print("=" * 80)
    ps.print_stats(30)
    print(s.getvalue())

    # Статистика по количеству вызовов
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s)
    ps.strip_dirs()
    ps.sort_stats('calls')

    print("\n" + "=" * 80)
    print("📈 ТОП-20 ФУНКЦИЙ ПО КОЛИЧЕСТВУ ВЫЗОВОВ")
    print("=" * 80)
    ps.print_stats(20)
    print(s.getvalue())

    print("\n" + "=" * 80)
    print("✅ Профилирование завершено")
    print("=" * 80)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("❌ Использование: python scripts/profile_replay_detail.py <replay_id>")
        print("   Пример: python scripts/profile_replay_detail.py 1")
        sys.exit(1)

    try:
        replay_id = int(sys.argv[1])
    except ValueError:
        print(f"❌ Некорректный ID реплея: {sys.argv[1]}")
        sys.exit(1)

    runs = 3
    if len(sys.argv) >= 3:
        try:
            runs = int(sys.argv[2])
        except ValueError:
            print(f"⚠️  Некорректное количество запусков: {sys.argv[2]}, используется значение по умолчанию: 3")

    profile_replay_detail(replay_id, runs)
