#!/usr/bin/env python3
"""
Скрипт для конвертации PNG/JPG изображений в WebP формат.

WebP обеспечивает на 25-35% меньший размер при том же качестве.
Создаёт WebP версии рядом с оригинальными файлами.

Usage:
    python scripts/convert_to_webp.py              # Dry run (показать что будет сделано)
    python scripts/convert_to_webp.py --apply      # Применить конвертацию
    python scripts/convert_to_webp.py --quality 90 # Задать качество (75-95)
    python scripts/convert_to_webp.py --clean      # Удалить все .webp файлы
"""

import argparse
import os
import sys
from pathlib import Path
from PIL import Image

# Добавляем корень проекта в путь
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Директории для сканирования
STATIC_DIR = BASE_DIR / "static"

# Минимальный размер для конвертации (в байтах)
MIN_SIZE_FOR_CONVERSION = 5 * 1024  # 5 KB

# Качество WebP по умолчанию (75-95, рекомендуется 80)
DEFAULT_QUALITY = 80


def format_bytes(bytes_size):
    """Форматирование размера в человекочитаемый вид."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"


def find_image_files(directory):
    """Найти все PNG/JPG файлы в директории."""
    image_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                image_files.append(Path(root) / file)
    return image_files


def convert_to_webp(file_path, quality=DEFAULT_QUALITY, dry_run=True):
    """
    Конвертировать изображение в WebP.

    Args:
        file_path: Путь к изображению
        quality: Качество WebP (75-95)
        dry_run: Если True, только показать что будет сделано

    Returns:
        tuple: (original_size, webp_size, saved_bytes, webp_path)
    """
    original_size = file_path.stat().st_size

    # Пропускаем маленькие файлы
    if original_size < MIN_SIZE_FOR_CONVERSION:
        return (original_size, 0, 0, None)

    # WebP путь (рядом с оригиналом)
    webp_path = file_path.with_suffix('.webp')

    # Если WebP уже существует, пропускаем
    if webp_path.exists() and not dry_run:
        return (original_size, webp_path.stat().st_size, 0, webp_path)

    if dry_run:
        # В dry run режиме только оцениваем размер
        return (original_size, 0, 0, webp_path)

    # Конвертируем в WebP
    try:
        img = Image.open(file_path)

        # Конвертируем в RGBA для PNG с прозрачностью или RGB для JPG
        if img.mode in ('RGBA', 'LA', 'P'):
            # Изображения с альфа-каналом
            if img.mode == 'P':
                img = img.convert('RGBA')
        else:
            # Обычные изображения
            if img.mode != 'RGB':
                img = img.convert('RGB')

        # Сохраняем как WebP
        # quality: 80 - оптимальный баланс качества/размера для WebP
        # method=6: максимальное сжатие (медленнее, но меньше размер)
        img.save(
            webp_path,
            'WEBP',
            quality=quality,
            method=6
        )

        webp_size = webp_path.stat().st_size
        saved_bytes = original_size - webp_size

        # Если WebP больше оригинала, удаляем его
        if saved_bytes < 0:
            webp_path.unlink()
            return (original_size, 0, 0, None)

        return (original_size, webp_size, saved_bytes, webp_path)

    except Exception as e:
        print(f"Ошибка при конвертации {file_path}: {e}")
        # Удаляем частично созданный файл
        if webp_path.exists():
            webp_path.unlink()
        return (original_size, 0, 0, None)


def clean_webp_files(directory):
    """Удалить все WebP файлы."""
    webp_files = list(directory.rglob('*.webp'))

    if not webp_files:
        print("WebP файлы не найдены!")
        return

    print(f"Найдено WebP файлов: {len(webp_files)}")
    print("\n⚠️  Будут удалены следующие файлы:")

    for webp_file in webp_files:
        print(f"  - {webp_file.relative_to(BASE_DIR)}")

    confirm = input("\nПродолжить? (yes/no): ")
    if confirm.lower() not in ('yes', 'y'):
        print("Отменено.")
        return

    deleted_count = 0
    for webp_file in webp_files:
        try:
            webp_file.unlink()
            deleted_count += 1
        except Exception as e:
            print(f"Ошибка при удалении {webp_file}: {e}")

    print(f"\n✅ Удалено файлов: {deleted_count}")


def main():
    parser = argparse.ArgumentParser(
        description='Конвертация изображений в WebP формат'
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Применить конвертацию (по умолчанию - dry run)'
    )
    parser.add_argument(
        '--clean',
        action='store_true',
        help='Удалить все WebP файлы'
    )
    parser.add_argument(
        '--quality',
        type=int,
        default=DEFAULT_QUALITY,
        help=f'Качество WebP (75-95, по умолчанию {DEFAULT_QUALITY})'
    )

    args = parser.parse_args()

    # Проверка качества
    if not 75 <= args.quality <= 95:
        print("❌ Качество должно быть в диапазоне 75-95")
        return

    # Очистка WebP файлов
    if args.clean:
        clean_webp_files(STATIC_DIR)
        return

    print("🔍 Поиск PNG/JPG файлов...")
    image_files = find_image_files(STATIC_DIR)
    print(f"Найдено изображений: {len(image_files)}")

    if not image_files:
        print("Изображения не найдены!")
        return

    if args.apply:
        print("\n⚙️  РЕЖИМ: Применение конвертации")
        print(f"🎨 Качество WebP: {args.quality}")
        print(f"📁 WebP файлы будут созданы рядом с оригинальными")
    else:
        print("\n👀 РЕЖИМ: Dry run (показать что будет сделано)")
        print("💡 Запустите с --apply для применения конвертации")

    print("\n" + "="*80)

    total_original = 0
    total_webp = 0
    total_saved = 0
    converted_count = 0
    skipped_count = 0

    for i, file_path in enumerate(image_files, 1):
        original_size, webp_size, saved_bytes, webp_path = convert_to_webp(
            file_path,
            quality=args.quality,
            dry_run=not args.apply
        )

        total_original += original_size

        if webp_size > 0:
            total_webp += webp_size
            total_saved += saved_bytes
            converted_count += 1

            reduction_percent = (saved_bytes / original_size) * 100

            print(f"[{i}/{len(image_files)}] {file_path.relative_to(BASE_DIR)}")
            print(f"    {format_bytes(original_size)} → {format_bytes(webp_size)} "
                  f"(↓ {reduction_percent:.1f}%)")
            if args.apply:
                print(f"    ✅ Создан: {webp_path.relative_to(BASE_DIR)}")

        elif original_size >= MIN_SIZE_FOR_CONVERSION and not args.apply:
            # Показываем файлы которые будут обработаны в dry run
            print(f"[{i}/{len(image_files)}] {file_path.relative_to(BASE_DIR)}")
            print(f"    {format_bytes(original_size)} (будет конвертирован)")
        else:
            skipped_count += 1

    print("\n" + "="*80)
    print("\n📊 СТАТИСТИКА:")
    print(f"Всего изображений: {len(image_files)}")

    if args.apply:
        print(f"Сконвертировано: {converted_count}")
        print(f"Пропущено: {skipped_count}")
        print(f"Исходный размер: {format_bytes(total_original)}")
        print(f"Размер WebP: {format_bytes(total_webp)}")
        print(f"Сэкономлено: {format_bytes(total_saved)} ({(total_saved/total_original)*100:.1f}%)")
        print(f"\n✅ Конвертация завершена!")
        print(f"\n💡 Теперь используйте template tag для автоматического выбора WebP:")
        print(f"    {{% load webp_tags %}}")
        print(f"    {{% webp_image 'path/to/image.png' 'Alt text' %}}")
    else:
        files_to_convert = len([f for f in image_files if f.stat().st_size >= MIN_SIZE_FOR_CONVERSION])
        print(f"Файлов для конвертации: {files_to_convert}")
        print(f"Общий размер: {format_bytes(total_original)}")
        print(f"\n💡 Запустите с --apply для применения конвертации")


if __name__ == '__main__':
    main()
