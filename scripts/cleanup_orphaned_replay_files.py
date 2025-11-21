#!/usr/bin/env python
"""
Скрипт для удаления файлов реплеев из файловой системы,
которые не привязаны ни к одной записи в базе данных.

Алгоритм:
1. Получаем список всех файлов из MEDIA_ROOT
2. Получаем список всех file_name из таблицы Replay
3. Находим файлы, которых нет в БД
4. Удаляем эти файлы (с опцией dry-run для предварительного просмотра)
"""
import sys
import os
from pathlib import Path
from typing import Set, List

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

    # Ищем все файлы .mtreplay в корне media и подпапках
    for file_path in media_root.rglob("*.mtreplay"):
        # Получаем относительный путь от media_root
        relative_path = file_path.relative_to(media_root)
        files.add(str(relative_path))

    return files


def get_files_from_database() -> Set[str]:
    """
    Получает список всех file_name из таблицы Replay.

    Returns:
        Множество имен файлов из БД
    """
    # Используем values_list для получения только file_name
    # flat=True возвращает простой список вместо кортежей
    file_names = Replay.objects.values_list('file_name', flat=True)

    # Нормализуем пути (заменяем прямые слеши на обратные для Windows)
    normalized = set()
    for name in file_names:
        # Преобразуем в Path и обратно в строку для нормализации
        normalized.add(str(Path(name)))

    return normalized


def cleanup_orphaned_files(dry_run: bool = True, skip_unsupported: bool = True) -> None:
    """
    Удаляет файлы реплеев, которые не привязаны к записям в БД.

    Args:
        dry_run: Если True, только показывает что будет удалено, не удаляет файлы
        skip_unsupported: Если True, пропускает файлы из папки unsupported_version_replays
    """
    print("=" * 80)
    print("ОЧИСТКА НЕИСПОЛЬЗУЕМЫХ ФАЙЛОВ РЕПЛЕЕВ")
    print("=" * 80)

    if dry_run:
        print("\n⚠️  РЕЖИМ ПРЕДПРОСМОТРА (dry_run=True)")
        print("   Файлы НЕ будут удалены\n")
    else:
        print("\n✅ РЕЖИМ УДАЛЕНИЯ (dry_run=False)")
        print("   Файлы БУДУТ удалены безвозвратно!\n")

        # Запрашиваем подтверждение
        confirm = input("⚠️  Вы уверены? Введите 'YES' для продолжения: ")
        if confirm != "YES":
            print("\n❌ Операция отменена")
            return

    media_root = Path(settings.MEDIA_ROOT)

    # Получаем списки файлов
    print("Сканирование файловой системы...")
    fs_files = get_files_from_filesystem(media_root)
    print(f"  Найдено файлов в {media_root}: {len(fs_files)}")

    print("\nПолучение списка файлов из БД...")
    db_files = get_files_from_database()
    print(f"  Записей в БД: {len(db_files)}")

    # Находим файлы-сироты (есть в FS, нет в БД)
    orphaned_files = fs_files - db_files

    # Фильтруем файлы из unsupported_version_replays, если нужно
    if skip_unsupported:
        orphaned_files_filtered = set()
        unsupported_count = 0

        for file_path in orphaned_files:
            if "unsupported_version_replays" in file_path:
                unsupported_count += 1
            else:
                orphaned_files_filtered.add(file_path)

        if unsupported_count > 0:
            print(f"\n📂 Пропущено файлов из unsupported_version_replays: {unsupported_count}")

        orphaned_files = orphaned_files_filtered

    if not orphaned_files:
        print("\n✅ Неиспользуемых файлов не найдено! Файловая система чистая.")
        return

    print(f"\n📋 Найдено неиспользуемых файлов: {len(orphaned_files)}")

    # Вычисляем размер файлов
    total_size = 0
    file_sizes: List[tuple[str, int]] = []

    for file_path in sorted(orphaned_files):
        full_path = media_root / file_path
        if full_path.exists():
            size = full_path.stat().st_size
            total_size += size
            file_sizes.append((file_path, size))

    # Форматируем размер
    def format_size(size_bytes: int) -> str:
        """Форматирует размер в читаемый вид."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    print(f"📊 Общий размер: {format_size(total_size)}")
    print("\nСписок файлов для удаления:\n")

    # Показываем первые 20 файлов
    max_display = 20
    for i, (file_path, size) in enumerate(file_sizes[:max_display], 1):
        print(f"  {i:3d}. {file_path:60s} ({format_size(size)})")

    if len(file_sizes) > max_display:
        print(f"  ... и ещё {len(file_sizes) - max_display} файлов")

    # Удаляем файлы
    if not dry_run:
        print("\n🗑️  Удаление файлов...\n")

        deleted_count = 0
        deleted_size = 0
        errors = []

        for file_path, size in file_sizes:
            full_path = media_root / file_path

            try:
                if full_path.exists():
                    full_path.unlink()
                    deleted_count += 1
                    deleted_size += size
                    print(f"  ✅ Удалено: {file_path}")
            except Exception as e:
                errors.append((file_path, str(e)))
                print(f"  ❌ Ошибка при удалении {file_path}: {e}")

        # Итоговая статистика
        print("\n" + "=" * 80)
        print("ИТОГОВАЯ СТАТИСТИКА")
        print("=" * 80)
        print(f"Удалено файлов:       {deleted_count} из {len(file_sizes)}")
        print(f"Освобождено места:    {format_size(deleted_size)}")

        if errors:
            print(f"\n⚠️  Ошибок при удалении: {len(errors)}")
            for file_path, error in errors:
                print(f"  - {file_path}: {error}")
    else:
        print("\n" + "=" * 80)
        print("ПРЕДВАРИТЕЛЬНЫЙ ПРОСМОТР")
        print("=" * 80)
        print(f"Будет удалено файлов: {len(file_sizes)}")
        print(f"Будет освобождено:    {format_size(total_size)}")
        print("\n💡 Для удаления файлов запустите:")
        print("   python scripts/cleanup_orphaned_replay_files.py --apply")

        if skip_unsupported:
            print("\n📌 Файлы из папки unsupported_version_replays будут пропущены.")
            print("   Для удаления всех файлов добавьте флаг --include-unsupported")

    print("=" * 80)


def main():
    """Главная функция."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Удаляет файлы реплеев, которые не привязаны к записям в БД"
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Применить удаление (по умолчанию только предпросмотр)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Режим предпросмотра (по умолчанию)'
    )
    parser.add_argument(
        '--include-unsupported',
        action='store_true',
        help='Включить файлы из папки unsupported_version_replays'
    )

    args = parser.parse_args()

    # Если указан --apply, отключаем dry_run
    dry_run = not args.apply
    skip_unsupported = not args.include_unsupported

    try:
        cleanup_orphaned_files(
            dry_run=dry_run,
            skip_unsupported=skip_unsupported
        )
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
