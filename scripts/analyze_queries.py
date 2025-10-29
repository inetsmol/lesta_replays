#!/usr/bin/env python
"""
Скрипт для анализа SQL запросов при обработке страницы деталей реплея.

Использование:
    python scripts/analyze_queries.py <replay_id>

Пример:
    python scripts/analyze_queries.py 1
"""

import os
import sys
import django
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# ВАЖНО: Включаем DEBUG для логирования SQL запросов
os.environ['DJANGO_DEBUG'] = 'True'

# Настраиваем Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lesta_replays.settings')
django.setup()

from django.test import RequestFactory
from django.db import connection
from django.db import reset_queries
from replays.views import ReplayDetailView
from replays.models import Replay


def analyze_queries(replay_id: int):
    """
    Анализирует SQL запросы при обработке страницы деталей реплея.

    Args:
        replay_id: ID реплея для анализа
    """
    try:
        replay = Replay.objects.select_related('tank', 'owner', 'user', 'map').get(pk=replay_id)
    except Replay.DoesNotExist:
        print(f"❌ Реплей с ID {replay_id} не найден")
        return

    print(f"🔍 Анализ SQL запросов для реплея ID={replay_id}")
    print(f"   Танк: {replay.tank.name if replay.tank else 'N/A'}")
    print(f"   Игрок: {replay.owner.real_name if replay.owner else 'N/A'}")
    print(f"   Дата боя: {replay.battle_date}\n")

    factory = RequestFactory()
    reset_queries()

    request = factory.get(f'/replays/{replay_id}/')
    view = ReplayDetailView()
    view.request = request
    view.object = replay

    try:
        context = view.get_context_data()
    except Exception as e:
        print(f"❌ Ошибка при выполнении: {e}")
        import traceback
        traceback.print_exc()
        return

    print("=" * 100)
    print(f"📊 ВСЕГО ВЫПОЛНЕНО ЗАПРОСОВ: {len(connection.queries)}")
    print("=" * 100)

    # Группируем запросы по типу
    query_types = {}
    for query in connection.queries:
        sql = query['sql'].strip()
        sql_type = sql.split()[0].upper()
        query_types[sql_type] = query_types.get(sql_type, 0) + 1

    print(f"\n📝 Статистика по типам запросов:")
    for sql_type, count in sorted(query_types.items()):
        print(f"   {sql_type:10s}: {count:3d} запросов")

    # Детальный вывод каждого запроса
    print(f"\n{'='*100}")
    print("🔎 ДЕТАЛЬНЫЙ СПИСОК ЗАПРОСОВ:")
    print(f"{'='*100}\n")

    for i, query in enumerate(connection.queries, 1):
        sql = query['sql'].strip()
        time = float(query['time']) * 1000  # в миллисекундах

        # Определяем таблицу из запроса
        if 'FROM' in sql.upper():
            table_start = sql.upper().index('FROM') + 5
            table_part = sql[table_start:].split()[0]
            table = table_part.strip('`"').split('.')[0]
        else:
            table = "N/A"

        print(f"Запрос #{i:2d} ({time:.3f} мс) - Таблица: {table}")
        print(f"   {sql[:200]}{'...' if len(sql) > 200 else ''}")
        print()

    # Поиск дублирующихся запросов
    sql_counts = {}
    for query in connection.queries:
        sql = query['sql'].strip()
        # Упрощаем SQL для поиска дубликатов (убираем конкретные ID)
        simplified = sql.split('WHERE')[0] if 'WHERE' in sql else sql
        sql_counts[simplified] = sql_counts.get(simplified, 0) + 1

    duplicates = {k: v for k, v in sql_counts.items() if v > 1}
    if duplicates:
        print(f"\n{'='*100}")
        print("⚠️  ОБНАРУЖЕНЫ ДУБЛИРУЮЩИЕСЯ ЗАПРОСЫ:")
        print(f"{'='*100}\n")
        for sql, count in sorted(duplicates.items(), key=lambda x: x[1], reverse=True):
            print(f"Повторений: {count}")
            print(f"   {sql[:200]}{'...' if len(sql) > 200 else ''}")
            print()

    print(f"{'='*100}")
    print("✅ Анализ завершён")
    print(f"{'='*100}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("❌ Использование: python scripts/analyze_queries.py <replay_id>")
        print("   Пример: python scripts/analyze_queries.py 1")
        sys.exit(1)

    try:
        replay_id = int(sys.argv[1])
    except ValueError:
        print(f"❌ Некорректный ID реплея: {sys.argv[1]}")
        sys.exit(1)

    analyze_queries(replay_id)
