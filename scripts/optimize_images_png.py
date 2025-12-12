#!/usr/bin/env python3
"""
Скрипт для оптимизации PNG изображений в проекте.

Использует Pillow для сжатия PNG с минимальной потерей качества.
Создаёт резервные копии перед оптимизацией.

Usage:
    python scripts/optimize_images_png.py              # Dry run (показать что будет сделано)
    python scripts/optimize_images_png.py --apply      # Применить оптимизацию
    python scripts/optimize_images_png.py --restore    # Восстановить из backup
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
from PIL import Image

# Добавляем корень проекта в путь
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Директории для сканирования
STATIC_DIR = BASE_DIR / "static"
BACKUP_DIR = BASE_DIR / "backups" / "images_backup"

# Минимальный размер для оптимизации (в байтах)
MIN_SIZE_FOR_OPTIMIZATION = 10 * 1024  # 10 KB


def format_bytes(bytes_size):
    """Форматирование размера в человекочитаемый вид."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"


def find_png_files(directory):
    """Найти все PNG файлы в директории."""
    png_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.lower().endswith('.png'):
                png_files.append(Path(root) / file)
    return png_files


def optimize_png(file_path, dry_run=True):
    """
    Оптимизировать PNG файл.

    Args:
        file_path: Путь к PNG файлу
        dry_run: Если True, только показать что будет сделано

    Returns:
        tuple: (original_size, new_size, saved_bytes)
    """
    original_size = file_path.stat().st_size

    # Пропускаем маленькие файлы
    if original_size < MIN_SIZE_FOR_OPTIMIZATION:
        return (original_size, original_size, 0)

    if dry_run:
        # В dry run режиме только оцениваем размер
        return (original_size, original_size, 0)

    # Создаём резервную копию
    backup_path = BACKUP_DIR / file_path.relative_to(STATIC_DIR)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file_path, backup_path)

    # Оптимизируем PNG
    try:
        img = Image.open(file_path)

        # Сохраняем с оптимизацией
        # optimize=True: Pillow найдёт оптимальные параметры сжатия
        img.save(file_path, 'PNG', optimize=True)

        new_size = file_path.stat().st_size
        saved_bytes = original_size - new_size

        return (original_size, new_size, saved_bytes)

    except Exception as e:
        print(f"Ошибка при оптимизации {file_path}: {e}")
        # Восстанавливаем из backup при ошибке
        if backup_path.exists():
            shutil.copy2(backup_path, file_path)
        return (original_size, original_size, 0)


def restore_from_backup():
    """Восстановить все файлы из backup."""
    if not BACKUP_DIR.exists():
        print("❌ Директория с backup не найдена!")
        return

    restored_count = 0
    for backup_file in BACKUP_DIR.rglob('*.png'):
        original_file = STATIC_DIR / backup_file.relative_to(BACKUP_DIR)
        if original_file.exists():
            shutil.copy2(backup_file, original_file)
            restored_count += 1
            print(f"✅ Восстановлен: {original_file.relative_to(BASE_DIR)}")

    print(f"\n📦 Восстановлено файлов: {restored_count}")


def main():
    parser = argparse.ArgumentParser(
        description='Оптимизация PNG изображений в проекте'
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Применить оптимизацию (по умолчанию - dry run)'
    )
    parser.add_argument(
        '--restore',
        action='store_true',
        help='Восстановить файлы из backup'
    )

    args = parser.parse_args()

    # Восстановление из backup
    if args.restore:
        restore_from_backup()
        return

    print("🔍 Поиск PNG файлов...")
    png_files = find_png_files(STATIC_DIR)
    print(f"Найдено PNG файлов: {len(png_files)}")

    if not png_files:
        print("PNG файлы не найдены!")
        return

    if args.apply:
        print("\n⚙️  РЕЖИМ: Применение оптимизации")
        print(f"📁 Backup будет создан в: {BACKUP_DIR}")
    else:
        print("\n👀 РЕЖИМ: Dry run (показать что будет сделано)")
        print("💡 Запустите с --apply для применения оптимизации")

    print("\n" + "="*80)

    total_original = 0
    total_optimized = 0
    total_saved = 0
    optimized_count = 0

    for i, file_path in enumerate(png_files, 1):
        original_size, new_size, saved_bytes = optimize_png(file_path, dry_run=not args.apply)

        total_original += original_size
        total_optimized += new_size if args.apply else original_size

        if saved_bytes > 0:
            total_saved += saved_bytes
            optimized_count += 1
            reduction_percent = (saved_bytes / original_size) * 100

            print(f"[{i}/{len(png_files)}] {file_path.relative_to(BASE_DIR)}")
            print(f"    {format_bytes(original_size)} → {format_bytes(new_size)} "
                  f"(↓ {reduction_percent:.1f}%)")

    print("\n" + "="*80)
    print("\n📊 СТАТИСТИКА:")
    print(f"Всего PNG файлов: {len(png_files)}")

    if args.apply:
        print(f"Оптимизировано файлов: {optimized_count}")
        print(f"Исходный размер: {format_bytes(total_original)}")
        print(f"Новый размер: {format_bytes(total_optimized)}")
        print(f"Сэкономлено: {format_bytes(total_saved)} ({(total_saved/total_original)*100:.1f}%)")
        print(f"\n✅ Оптимизация завершена!")
        print(f"📦 Backup сохранён в: {BACKUP_DIR}")
        print(f"💡 Для восстановления запустите: python {__file__} --restore")
    else:
        print(f"Файлов для оптимизации: {optimized_count}")
        print(f"Общий размер: {format_bytes(total_original)}")
        print(f"\n💡 Запустите с --apply для применения оптимизации")


if __name__ == '__main__':
    main()
