#!/usr/bin/env python3
"""
Скрипт для оптимизации JPG/JPEG изображений в проекте.

Использует Pillow для сжатия JPG с оптимальным качеством (85%).
Создаёт резервные копии перед оптимизацией.

Usage:
    python scripts/optimize_images_jpg.py              # Dry run (показать что будет сделано)
    python scripts/optimize_images_jpg.py --apply      # Применить оптимизацию
    python scripts/optimize_images_jpg.py --restore    # Восстановить из backup
    python scripts/optimize_images_jpg.py --quality 90 # Задать качество (75-95)
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

# Качество JPG по умолчанию (75-95, рекомендуется 85)
DEFAULT_QUALITY = 85


def format_bytes(bytes_size):
    """Форматирование размера в человекочитаемый вид."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"


def find_jpg_files(directory):
    """Найти все JPG/JPEG файлы в директории."""
    jpg_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg')):
                jpg_files.append(Path(root) / file)
    return jpg_files


def optimize_jpg(file_path, quality=DEFAULT_QUALITY, dry_run=True):
    """
    Оптимизировать JPG файл.

    Args:
        file_path: Путь к JPG файлу
        quality: Качество сжатия (75-95)
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

    # Оптимизируем JPG
    try:
        img = Image.open(file_path)

        # Конвертируем в RGB если необходимо (для CMYK и других форматов)
        if img.mode != 'RGB':
            img = img.convert('RGB')

        # Сохраняем с оптимизацией
        # quality: 85 - оптимальный баланс качества/размера
        # optimize=True: Pillow найдёт оптимальные параметры сжатия
        # progressive=True: прогрессивная загрузка (сначала low-res, потом full)
        img.save(
            file_path,
            'JPEG',
            quality=quality,
            optimize=True,
            progressive=True,
            subsampling='4:2:0'  # стандартная субдискретизация цвета
        )

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
    for backup_file in BACKUP_DIR.rglob('*.jpg'):
        original_file = STATIC_DIR / backup_file.relative_to(BACKUP_DIR)
        if original_file.exists():
            shutil.copy2(backup_file, original_file)
            restored_count += 1
            print(f"✅ Восстановлен: {original_file.relative_to(BASE_DIR)}")

    for backup_file in BACKUP_DIR.rglob('*.jpeg'):
        original_file = STATIC_DIR / backup_file.relative_to(BACKUP_DIR)
        if original_file.exists():
            shutil.copy2(backup_file, original_file)
            restored_count += 1
            print(f"✅ Восстановлен: {original_file.relative_to(BASE_DIR)}")

    print(f"\n📦 Восстановлено файлов: {restored_count}")


def main():
    parser = argparse.ArgumentParser(
        description='Оптимизация JPG/JPEG изображений в проекте'
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
    parser.add_argument(
        '--quality',
        type=int,
        default=DEFAULT_QUALITY,
        help=f'Качество JPG (75-95, по умолчанию {DEFAULT_QUALITY})'
    )

    args = parser.parse_args()

    # Проверка качества
    if not 75 <= args.quality <= 95:
        print("❌ Качество должно быть в диапазоне 75-95")
        return

    # Восстановление из backup
    if args.restore:
        restore_from_backup()
        return

    print("🔍 Поиск JPG/JPEG файлов...")
    jpg_files = find_jpg_files(STATIC_DIR)
    print(f"Найдено JPG/JPEG файлов: {len(jpg_files)}")

    if not jpg_files:
        print("JPG/JPEG файлы не найдены!")
        return

    if args.apply:
        print("\n⚙️  РЕЖИМ: Применение оптимизации")
        print(f"🎨 Качество JPG: {args.quality}")
        print(f"📁 Backup будет создан в: {BACKUP_DIR}")
    else:
        print("\n👀 РЕЖИМ: Dry run (показать что будет сделано)")
        print("💡 Запустите с --apply для применения оптимизации")

    print("\n" + "="*80)

    total_original = 0
    total_optimized = 0
    total_saved = 0
    optimized_count = 0

    for i, file_path in enumerate(jpg_files, 1):
        original_size, new_size, saved_bytes = optimize_jpg(
            file_path,
            quality=args.quality,
            dry_run=not args.apply
        )

        total_original += original_size
        total_optimized += new_size if args.apply else original_size

        if saved_bytes > 0:
            total_saved += saved_bytes
            optimized_count += 1
            reduction_percent = (saved_bytes / original_size) * 100

            print(f"[{i}/{len(jpg_files)}] {file_path.relative_to(BASE_DIR)}")
            print(f"    {format_bytes(original_size)} → {format_bytes(new_size)} "
                  f"(↓ {reduction_percent:.1f}%)")
        elif original_size >= MIN_SIZE_FOR_OPTIMIZATION and not args.apply:
            # Показываем файлы которые будут обработаны в dry run
            print(f"[{i}/{len(jpg_files)}] {file_path.relative_to(BASE_DIR)}")
            print(f"    {format_bytes(original_size)} (будет оптимизирован)")

    print("\n" + "="*80)
    print("\n📊 СТАТИСТИКА:")
    print(f"Всего JPG/JPEG файлов: {len(jpg_files)}")

    if args.apply:
        print(f"Оптимизировано файлов: {optimized_count}")
        print(f"Исходный размер: {format_bytes(total_original)}")
        print(f"Новый размер: {format_bytes(total_optimized)}")
        print(f"Сэкономлено: {format_bytes(total_saved)} ({(total_saved/total_original)*100:.1f}%)")
        print(f"\n✅ Оптимизация завершена!")
        print(f"📦 Backup сохранён в: {BACKUP_DIR}")
        print(f"💡 Для восстановления запустите: python {__file__} --restore")
    else:
        files_to_optimize = len([f for f in jpg_files if f.stat().st_size >= MIN_SIZE_FOR_OPTIMIZATION])
        print(f"Файлов для оптимизации: {files_to_optimize}")
        print(f"Общий размер: {format_bytes(total_original)}")
        print(f"\n💡 Запустите с --apply для применения оптимизации")


if __name__ == '__main__':
    main()
