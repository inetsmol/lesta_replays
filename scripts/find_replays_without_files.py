#!/usr/bin/env python
"""
Скрипт для поиска записей реплеев в БД, у которых отсутствуют файлы на диске.

Использование:
    python scripts/find_replays_without_files.py
"""
import sys
import os
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Настраиваем Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lesta_replays.settings")
import django
django.setup()

from django.conf import settings
from replays.models import Replay


def main():
    """Главная функция."""
    print("=" * 80)
    print("ПОИСК РЕПЛЕЕВ БЕЗ ФАЙЛОВ")
    print("=" * 80)

    print("\nПолучение списка реплеев из БД...")
    all_replays = Replay.objects.all()
    total_count = all_replays.count()
    print(f"Всего записей в БД: {total_count}")

    if total_count == 0:
        print("\n✅ База данных пуста!")
        return

    print("\nПроверка существования файлов...")
    missing_replays = []
    media_root = Path(settings.MEDIA_ROOT)

    for i, replay in enumerate(all_replays.iterator(chunk_size=100), 1):
        if i % 100 == 0:
            print(f"Проверено: {i}/{total_count} ({i/total_count*100:.1f}%)", end='\r')

        # Получаем путь к файлу
        if replay.file_name:
            file_path = media_root / replay.file_name
            if not file_path.exists():
                missing_replays.append(replay)
        else:
            missing_replays.append(replay)

    print(f"Проверено: {total_count}/{total_count} (100.0%)")

    # Вывод результатов
    print("\n" + "=" * 80)

    if not missing_replays:
        print("✅ Все записи в БД имеют файлы на диске!")
    else:
        print(f"❌ Найдено записей без файлов: {len(missing_replays)}")
        print("\n" + f"{'ID':>6} | {'Дата боя':<19}")
        print("-" * 30)

        for replay in missing_replays:
            battle_date = replay.battle_date.strftime('%Y-%m-%d %H:%M:%S') if replay.battle_date else 'N/A'
            print(f"{replay.id:>6} | {battle_date:<19}")

    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
