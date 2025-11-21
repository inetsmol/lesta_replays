#!/usr/bin/env python
"""
Скрипт для исправления file_name в базе данных для реплеев,
у которых файл был переименован при загрузке, но в БД записалось старое имя.

Алгоритм:
1. Находим все реплеи, у которых файл не существует на диске
2. Для каждого пытаемся найти похожий файл с timestamp
3. Обновляем file_name в БД
"""
import sys
import os
import re
from pathlib import Path
from typing import Optional, List

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Настраиваем Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lesta_replays.settings")
import django
django.setup()

from django.conf import settings
from replays.models import Replay


def find_renamed_file(original_name: str, media_root: Path, replay_created_at=None) -> Optional[str]:
    """
    Ищет файл, который был переименован с добавлением timestamp.

    Например, для "test.mtreplay" ищет "test_20251121123456.mtreplay"

    Args:
        original_name: Оригинальное имя файла
        media_root: Путь к папке media
        replay_created_at: Время создания реплея в БД (для точного сопоставления)

    Returns:
        Новое имя файла или None, если не найдено
    """
    from datetime import datetime

    # Разбираем имя файла
    path = Path(original_name)
    stem = path.stem  # имя без расширения
    suffix = path.suffix  # расширение с точкой

    # Паттерн для поиска: stem_YYYYMMDDHHMMSS.suffix
    # Пример: test_20251121123456.mtreplay
    pattern = re.escape(stem) + r'_(\d{14})' + re.escape(suffix)

    # Ищем все файлы в media_root
    candidates: List[tuple[Path, str, datetime]] = []

    for file_path in media_root.glob(f"*{suffix}"):
        match = re.match(pattern, file_path.name)
        if match:
            timestamp_str = match.group(1)
            # Парсим timestamp: YYYYMMDDHHMMSS -> datetime
            try:
                file_datetime = datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
                candidates.append((file_path, timestamp_str, file_datetime))
            except ValueError:
                # Некорректный timestamp, пропускаем
                continue

    if not candidates:
        return None

    # Если передан replay_created_at, ищем файл с ближайшим временем
    if replay_created_at:
        # Убираем timezone для корректного сравнения
        if replay_created_at.tzinfo:
            replay_created_at = replay_created_at.replace(tzinfo=None)

        # Сортируем по разнице во времени (меньше = ближе)
        candidates.sort(key=lambda x: abs((x[2] - replay_created_at).total_seconds()))
        return candidates[0][0].name
    else:
        # Если времени нет, возвращаем файл с самым поздним timestamp (старое поведение)
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0].name


def fix_replay_filenames(dry_run: bool = True) -> None:
    """
    Исправляет file_name в БД для реплеев с несуществующими файлами.

    Args:
        dry_run: Если True, только показывает что будет исправлено, не меняет БД
    """
    print("=" * 80)
    print("ИСПРАВЛЕНИЕ FILE_NAME ДЛЯ РЕПЛЕЕВ")
    print("=" * 80)

    if dry_run:
        print("\n⚠️  РЕЖИМ ПРЕДПРОСМОТРА (dry_run=True)")
        print("   Изменения НЕ будут внесены в базу данных\n")
    else:
        print("\n✅ РЕЖИМ ИСПРАВЛЕНИЯ (dry_run=False)")
        print("   Изменения БУДУТ внесены в базу данных\n")

    media_root = Path(settings.MEDIA_ROOT)

    # Статистика
    total_replays = Replay.objects.count()
    broken_replays = []
    fixed_replays = []
    unfixable_replays = []

    print(f"Всего реплеев в БД: {total_replays}\n")
    print("Проверка реплеев...")

    # Находим проблемные реплеи
    for replay in Replay.objects.all():
        file_path = media_root / replay.file_name

        if not file_path.exists():
            broken_replays.append(replay)
            print(f"  ❌ ID {replay.id}: файл не найден - {replay.file_name}")

    if not broken_replays:
        print("\n✅ Все реплеи в порядке! Проблемных файлов не найдено.")
        return

    print(f"\n📋 Найдено проблемных реплеев: {len(broken_replays)}")
    print("\nПоиск переименованных файлов...\n")

    # Пытаемся исправить
    for replay in broken_replays:
        # ВАЖНО: Передаем replay.created_at для точного сопоставления по времени
        new_filename = find_renamed_file(replay.file_name, media_root, replay.created_at)

        if new_filename:
            fixed_replays.append((replay, new_filename))
            print(f"  ✅ ID {replay.id}:")
            print(f"     Старое: {replay.file_name}")
            print(f"     Новое:  {new_filename}")
            print(f"     Создан: {replay.created_at}")

            if not dry_run:
                replay.file_name = new_filename
                replay.save(update_fields=['file_name'])
                print(f"     → Сохранено в БД")
        else:
            unfixable_replays.append(replay)
            print(f"  ⚠️  ID {replay.id}: переименованный файл НЕ найден")
            print(f"     Имя: {replay.file_name}")
            print(f"     Создан: {replay.created_at}")

    # Итоговая статистика
    print("\n" + "=" * 80)
    print("ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 80)
    print(f"Всего реплеев:           {total_replays}")
    print(f"Проблемных:              {len(broken_replays)}")
    print(f"Исправлено:              {len(fixed_replays)}")
    print(f"Не удалось исправить:    {len(unfixable_replays)}")

    if unfixable_replays:
        print("\n⚠️  Реплеи, которые не удалось исправить:")
        for replay in unfixable_replays:
            print(f"  ID {replay.id}: {replay.file_name}")
            print(f"  Возможные действия:")
            print(f"    1. Удалить реплей из БД")
            print(f"    2. Повторно загрузить файл реплея")

    if dry_run and fixed_replays:
        print("\n💡 Для применения изменений запустите:")
        print("   .venv/bin/python scripts/fix_duplicate_filenames.py --apply")

    print("=" * 80)


def main():
    """Главная функция."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Исправляет file_name в БД для реплеев с переименованными файлами"
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Применить изменения в БД (по умолчанию только предпросмотр)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Режим предпросмотра (по умолчанию)'
    )

    args = parser.parse_args()

    # Если указан --apply, отключаем dry_run
    dry_run = not args.apply

    try:
        fix_replay_filenames(dry_run=dry_run)
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
