#!/usr/bin/env python
"""
Скрипт для перемещения файлов реплеев, которые не привязаны к записям в БД,
в отдельную папку media/orphaned_replays для последующей обработки.

Алгоритм:
1. Получаем список всех файлов из MEDIA_ROOT
2. Получаем список всех file_name из таблицы Replay
3. Находим файлы, которых нет в БД (файлы-сироты)
4. Перемещаем эти файлы в media/orphaned_replays
"""
import sys
import os
import shutil
from pathlib import Path
from typing import Set, List
from datetime import datetime

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Настраиваем Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lesta_replays.settings")
import django
django.setup()

from django.conf import settings
from replays.models import Replay


def get_files_from_filesystem(media_root: Path) -> Set[str]:
    """
    Получает список всех файлов .mtreplay из MEDIA_ROOT.

    Args:
        media_root: Путь к папке media

    Returns:
        Множество имен файлов
    """
    if not media_root.exists():
        print(f"⚠️  Папка {media_root} не существует!")
        return set()

    files = set()

    # Ищем только файлы .mtreplay в корне media (не в подпапках)
    for file_path in media_root.glob("*.mtreplay"):
        files.add(file_path.name)

    return files


def get_files_from_database() -> Set[str]:
    """
    Получает список всех file_name из таблицы Replay.

    Returns:
        Множество имен файлов из БД
    """
    # Используем values_list для получения только file_name
    file_names = Replay.objects.values_list('file_name', flat=True)

    # Нормализуем пути - извлекаем только имя файла
    normalized = set()
    for name in file_names:
        # Извлекаем только имя файла (на случай если хранятся пути)
        file_name = Path(name).name
        normalized.add(file_name)

    return normalized


def move_orphaned_files(dry_run: bool = True) -> None:
    """
    Перемещает файлы реплеев, которые не привязаны к записям в БД,
    в папку orphaned_replays.

    Args:
        dry_run: Если True, только показывает что будет перемещено
    """
    print("=" * 80)
    print("ПЕРЕМЕЩЕНИЕ НЕИСПОЛЬЗУЕМЫХ ФАЙЛОВ РЕПЛЕЕВ")
    print("=" * 80)

    if dry_run:
        print("\n⚠️  РЕЖИМ ПРЕДПРОСМОТРА (dry_run=True)")
        print("   Файлы НЕ будут перемещены\n")
    else:
        print("\n✅ РЕЖИМ ПЕРЕМЕЩЕНИЯ (dry_run=False)")
        print("   Файлы БУДУТ перемещены в media/orphaned_replays\n")

    media_root = Path(settings.MEDIA_ROOT)
    orphaned_dir = media_root / "orphaned_replays"

    # Получаем списки файлов
    print("Сканирование файловой системы...")
    fs_files = get_files_from_filesystem(media_root)
    print(f"  Найдено файлов в {media_root}: {len(fs_files)}")

    print("\nПолучение списка файлов из БД...")
    db_files = get_files_from_database()
    print(f"  Записей в БД: {len(db_files)}")

    # Находим файлы-сироты (есть в FS, нет в БД)
    orphaned_files = fs_files - db_files

    if not orphaned_files:
        print("\n✅ Неиспользуемых файлов не найдено! Все файлы привязаны к БД.")
        return

    print(f"\n📋 Найдено неиспользуемых файлов: {len(orphaned_files)}")

    # Вычисляем размер файлов
    total_size = 0
    file_sizes: List[tuple[str, int]] = []

    for file_name in sorted(orphaned_files):
        full_path = media_root / file_name
        if full_path.exists():
            size = full_path.stat().st_size
            total_size += size
            file_sizes.append((file_name, size))

    # Форматируем размер
    def format_size(size_bytes: int) -> str:
        """Форматирует размер в читаемый вид."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    print(f"📊 Общий размер: {format_size(total_size)}")
    print(f"📂 Целевая папка: {orphaned_dir}")
    print("\nСписок файлов для перемещения:\n")

    # Показываем первые 20 файлов
    max_display = 20
    for i, (file_name, size) in enumerate(file_sizes[:max_display], 1):
        print(f"  {i:3d}. {file_name:60s} ({format_size(size)})")

    if len(file_sizes) > max_display:
        print(f"  ... и ещё {len(file_sizes) - max_display} файлов")

    # Перемещаем файлы
    if not dry_run:
        # Создаём папку orphaned_replays с timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_dir = orphaned_dir / timestamp
        target_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n📦 Создана папка: {target_dir}")
        print("\n🔄 Перемещение файлов...\n")

        moved_count = 0
        moved_size = 0
        errors = []

        for file_name, size in file_sizes:
            src_path = media_root / file_name
            dst_path = target_dir / file_name

            try:
                if src_path.exists():
                    shutil.move(str(src_path), str(dst_path))
                    moved_count += 1
                    moved_size += size
                    print(f"  ✅ Перемещено: {file_name}")
            except Exception as e:
                errors.append((file_name, str(e)))
                print(f"  ❌ Ошибка при перемещении {file_name}: {e}")

        # Создаём информационный файл
        info_file = target_dir / "README.txt"
        with open(info_file, "w", encoding="utf-8") as f:
            f.write(f"Файлы реплеев, не привязанные к записям в БД\n")
            f.write(f"Дата перемещения: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Количество файлов: {moved_count}\n")
            f.write(f"Общий размер: {format_size(moved_size)}\n")
            f.write(f"\nДля загрузки этих файлов в БД используйте:\n")
            f.write(f"python scripts/import_orphaned_replays.py --source {timestamp}\n")

        # Итоговая статистика
        print("\n" + "=" * 80)
        print("ИТОГОВАЯ СТАТИСТИКА")
        print("=" * 80)
        print(f"Перемещено файлов:    {moved_count} из {len(file_sizes)}")
        print(f"Общий размер:         {format_size(moved_size)}")
        print(f"Папка назначения:     {target_dir}")

        if errors:
            print(f"\n⚠️  Ошибок при перемещении: {len(errors)}")
            for file_name, error in errors:
                print(f"  - {file_name}: {error}")

        print("\n💡 Для загрузки файлов в БД используйте:")
        print(f"   python scripts/import_orphaned_replays.py --source {timestamp}")

    else:
        print("\n" + "=" * 80)
        print("ПРЕДВАРИТЕЛЬНЫЙ ПРОСМОТР")
        print("=" * 80)
        print(f"Будет перемещено файлов: {len(file_sizes)}")
        print(f"Общий размер:            {format_size(total_size)}")
        print(f"Папка назначения:        {orphaned_dir / datetime.now().strftime('%Y%m%d_%H%M%S')}")
        print("\n💡 Для перемещения файлов запустите:")
        print("   python scripts/move_orphaned_replays.py --apply")

    print("=" * 80)


def main():
    """Главная функция."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Перемещает файлы реплеев, не привязанные к БД, в orphaned_replays"
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Применить перемещение (по умолчанию только предпросмотр)'
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
        move_orphaned_files(dry_run=dry_run)
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
