#!/usr/bin/env python
"""
Скрипт для бенчмаркинга (сравнения производительности) обработки страницы деталей реплея.

Использование:
    python scripts/benchmark_replay_detail.py <replay_id> [runs]

Пример:
    python scripts/benchmark_replay_detail.py 1 10
"""

import os
import sys
import django
import time
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Настраиваем Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lesta_replays.settings')
django.setup()

from django.test import RequestFactory
from django.db import connection
from django.db import reset_queries
from replays.views import ReplayDetailView
from replays.models import Replay


def benchmark_replay_detail(replay_id: int, runs: int = 10):
    """
    Измеряет производительность обработки страницы деталей реплея.

    Args:
        replay_id: ID реплея для бенчмаркинга
        runs: Количество запусков для усреднения результатов
    """
    try:
        replay = Replay.objects.select_related('tank', 'owner', 'user', 'map').get(pk=replay_id)
    except Replay.DoesNotExist:
        print(f"❌ Реплей с ID {replay_id} не найден")
        return

    print(f"🔥 Бенчмарк реплея ID={replay_id}")
    print(f"   Танк: {replay.tank.name if replay.tank else 'N/A'}")
    print(f"   Игрок: {replay.owner.real_name if replay.owner else 'N/A'}")
    print(f"   Дата боя: {replay.battle_date}")
    print(f"   Запусков: {runs}\n")

    factory = RequestFactory()
    times = []
    query_counts = []

    # Прогреваем кеш
    request = factory.get(f'/replays/{replay_id}/')
    view = ReplayDetailView()
    view.request = request
    view.object = replay
    try:
        _ = view.get_context_data()
    except Exception as e:
        print(f"❌ Ошибка при прогреве: {e}")
        return

    print("⏱️  Запуск бенчмарка...")

    for i in range(runs):
        reset_queries()

        request = factory.get(f'/replays/{replay_id}/')
        view = ReplayDetailView()
        view.request = request
        view.object = replay

        start_time = time.perf_counter()
        try:
            context = view.get_context_data()
        except Exception as e:
            print(f"❌ Ошибка при запуске {i+1}: {e}")
            continue
        end_time = time.perf_counter()

        elapsed = (end_time - start_time) * 1000  # в миллисекундах
        times.append(elapsed)
        query_counts.append(len(connection.queries))

        print(f"   Запуск {i+1:2d}: {elapsed:6.2f} мс, SQL запросов: {len(connection.queries)}")

    if not times:
        print("❌ Не удалось выполнить ни одного успешного запуска")
        return

    # Вычисляем статистику
    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)
    avg_queries = sum(query_counts) / len(query_counts)

    print("\n" + "=" * 80)
    print("📊 РЕЗУЛЬТАТЫ БЕНЧМАРКА")
    print("=" * 80)
    print(f"Среднее время:       {avg_time:6.2f} мс")
    print(f"Минимальное время:   {min_time:6.2f} мс")
    print(f"Максимальное время:  {max_time:6.2f} мс")
    print(f"Среднее SQL запросов: {avg_queries:5.1f}")
    print("=" * 80)

    # Подсчитываем уникальные типы запросов
    reset_queries()
    request = factory.get(f'/replays/{replay_id}/')
    view = ReplayDetailView()
    view.request = request
    view.object = replay
    _ = view.get_context_data()

    print(f"\n📝 Детализация SQL запросов (последний запуск):")
    query_types = {}
    for query in connection.queries:
        sql = query['sql'].strip().split()[0].upper()
        query_types[sql] = query_types.get(sql, 0) + 1

    for sql_type, count in sorted(query_types.items()):
        print(f"   {sql_type:10s}: {count:3d} запросов")

    print(f"\n✅ Бенчмарк завершён")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("❌ Использование: python scripts/benchmark_replay_detail.py <replay_id> [runs]")
        print("   Пример: python scripts/benchmark_replay_detail.py 1 10")
        sys.exit(1)

    try:
        replay_id = int(sys.argv[1])
    except ValueError:
        print(f"❌ Некорректный ID реплея: {sys.argv[1]}")
        sys.exit(1)

    runs = 10
    if len(sys.argv) >= 3:
        try:
            runs = int(sys.argv[2])
        except ValueError:
            print(f"⚠️  Некорректное количество запусков: {sys.argv[2]}, используется значение по умолчанию: 10")

    benchmark_replay_detail(replay_id, runs)
