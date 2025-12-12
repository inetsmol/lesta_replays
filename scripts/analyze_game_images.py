#!/usr/bin/env python3
"""
Скрипт для анализа изображений танков, карт и иконок в проекте.

Проверяет:
- Наличие изображений для всех танков/карт в БД
- Размеры файлов
- Отсутствующие файлы
- Возможность оптимизации

Usage:
    python scripts/analyze_game_images.py              # Общий анализ
    python scripts/analyze_game_images.py --missing    # Только отсутствующие
    python scripts/analyze_game_images.py --large      # Файлы > 100KB
"""

import argparse
import os
import sys
from pathlib import Path
from collections import defaultdict

# Добавляем корень проекта в путь
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lesta_replays.settings')
import django
django.setup()

from django.contrib.staticfiles.storage import staticfiles_storage
from replays.models import Tank, Map


def format_bytes(bytes_size):
    """Форматирование размера в человекочитаемый вид."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"


def check_tank_images():
    """Проверить изображения танков."""
    print("\n" + "="*80)
    print("АНАЛИЗ ИЗОБРАЖЕНИЙ ТАНКОВ")
    print("="*80)

    tanks = Tank.objects.all()
    print(f"\nВсего танков в БД: {tanks.count()}")

    stats = {
        'total': 0,
        'found': 0,
        'missing': [],
        'large': [],  # > 100KB
        'total_size': 0,
    }

    for tank in tanks:
        stats['total'] += 1

        # Путь к изображению танка
        image_path = f'style/images/wot/shop/vehicles/180x135/{tank.vehicleId}.png'

        try:
            # Проверяем существование файла
            if staticfiles_storage.exists(image_path):
                stats['found'] += 1

                # Получаем полный путь к файлу
                full_path = staticfiles_storage.path(image_path)
                if os.path.exists(full_path):
                    file_size = os.path.getsize(full_path)
                    stats['total_size'] += file_size

                    # Файлы > 100KB
                    if file_size > 100 * 1024:
                        stats['large'].append({
                            'tank': tank.name,
                            'vehicle_id': tank.vehicleId,
                            'size': file_size,
                            'path': image_path
                        })
            else:
                stats['missing'].append({
                    'tank': tank.name,
                    'vehicle_id': tank.vehicleId,
                    'path': image_path
                })
        except Exception as e:
            stats['missing'].append({
                'tank': tank.name,
                'vehicle_id': tank.vehicleId,
                'path': image_path,
                'error': str(e)
            })

    # Вывод статистики
    print(f"\n📊 Статистика:")
    print(f"Найдено изображений: {stats['found']}/{stats['total']}")
    print(f"Отсутствует: {len(stats['missing'])}")
    print(f"Общий размер: {format_bytes(stats['total_size'])}")

    if stats['found'] > 0:
        avg_size = stats['total_size'] / stats['found']
        print(f"Средний размер: {format_bytes(avg_size)}")

    # Отсутствующие файлы
    if stats['missing']:
        print(f"\n⚠️  Отсутствующие изображения танков ({len(stats['missing'])}):")
        for item in stats['missing'][:10]:  # Показываем первые 10
            print(f"  - {item['tank']} ({item['vehicle_id']})")
        if len(stats['missing']) > 10:
            print(f"  ... и ещё {len(stats['missing']) - 10}")

    # Большие файлы
    if stats['large']:
        print(f"\n📦 Большие файлы (> 100KB, {len(stats['large'])}):")
        stats['large'].sort(key=lambda x: x['size'], reverse=True)
        for item in stats['large'][:10]:  # Топ 10 самых больших
            print(f"  - {item['tank']}: {format_bytes(item['size'])}")
        if len(stats['large']) > 10:
            print(f"  ... и ещё {len(stats['large']) - 10}")

    return stats


def check_map_images():
    """Проверить изображения карт."""
    print("\n" + "="*80)
    print("АНАЛИЗ ИЗОБРАЖЕНИЙ КАРТ")
    print("="*80)

    maps = Map.objects.all()
    print(f"\nВсего карт в БД: {maps.count()}")

    stats = {
        'total': 0,
        'found': 0,
        'missing': [],
        'large': [],  # > 100KB
        'total_size': 0,
    }

    for map_obj in maps:
        stats['total'] += 1

        # Путь к изображению карты
        image_path = f'style/images/wot/map/stats/{map_obj.map_name}.png'

        try:
            # Проверяем существование файла
            if staticfiles_storage.exists(image_path):
                stats['found'] += 1

                # Получаем полный путь к файлу
                full_path = staticfiles_storage.path(image_path)
                if os.path.exists(full_path):
                    file_size = os.path.getsize(full_path)
                    stats['total_size'] += file_size

                    # Файлы > 100KB
                    if file_size > 100 * 1024:
                        stats['large'].append({
                            'map': map_obj.map_display_name or map_obj.map_name,
                            'map_name': map_obj.map_name,
                            'size': file_size,
                            'path': image_path
                        })
            else:
                stats['missing'].append({
                    'map': map_obj.map_display_name or map_obj.map_name,
                    'map_name': map_obj.map_name,
                    'path': image_path
                })
        except Exception as e:
            stats['missing'].append({
                'map': map_obj.map_display_name or map_obj.map_name,
                'map_name': map_obj.map_name,
                'path': image_path,
                'error': str(e)
            })

    # Вывод статистики
    print(f"\n📊 Статистика:")
    print(f"Найдено изображений: {stats['found']}/{stats['total']}")
    print(f"Отсутствует: {len(stats['missing'])}")
    print(f"Общий размер: {format_bytes(stats['total_size'])}")

    if stats['found'] > 0:
        avg_size = stats['total_size'] / stats['found']
        print(f"Средний размер: {format_bytes(avg_size)}")

    # Отсутствующие файлы
    if stats['missing']:
        print(f"\n⚠️  Отсутствующие изображения карт ({len(stats['missing'])}):")
        for item in stats['missing']:
            print(f"  - {item['map']} ({item['map_name']})")

    # Большие файлы
    if stats['large']:
        print(f"\n📦 Большие файлы (> 100KB, {len(stats['large'])}):")
        stats['large'].sort(key=lambda x: x['size'], reverse=True)
        for item in stats['large']:
            print(f"  - {item['map']}: {format_bytes(item['size'])}")

    return stats


def check_icon_directories():
    """Проверить размеры директорий с иконками."""
    print("\n" + "="*80)
    print("АНАЛИЗ ДИРЕКТОРИЙ ИКОНОК")
    print("="*80)

    icon_dirs = [
        'style/images/wot/library',
        'style/images/wot/vehicleTypes',
        'style/images/wot/levels',
        'style/images/wot/buttons',
        'style/images/wot/achievement/big',
    ]

    for icon_dir in icon_dirs:
        try:
            if staticfiles_storage.exists(icon_dir):
                full_path = staticfiles_storage.path(icon_dir)
                if os.path.isdir(full_path):
                    # Подсчитываем размер директории
                    total_size = 0
                    file_count = 0
                    for root, dirs, files in os.walk(full_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            if os.path.isfile(file_path):
                                total_size += os.path.getsize(file_path)
                                file_count += 1

                    print(f"\n📁 {icon_dir}")
                    print(f"   Файлов: {file_count}")
                    print(f"   Размер: {format_bytes(total_size)}")
        except Exception as e:
            print(f"\n❌ Ошибка при проверке {icon_dir}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='Анализ изображений танков, карт и иконок'
    )
    parser.add_argument(
        '--missing',
        action='store_true',
        help='Показать только отсутствующие файлы'
    )
    parser.add_argument(
        '--large',
        action='store_true',
        help='Показать только большие файлы (> 100KB)'
    )

    args = parser.parse_args()

    print("🔍 АНАЛИЗ ИГРОВЫХ ИЗОБРАЖЕНИЙ")
    print("="*80)

    # Проверка танков
    tank_stats = check_tank_images()

    # Проверка карт
    map_stats = check_map_images()

    # Проверка иконок
    check_icon_directories()

    # Общая статистика
    print("\n" + "="*80)
    print("ОБЩАЯ СТАТИСТИКА")
    print("="*80)

    total_found = tank_stats['found'] + map_stats['found']
    total_missing = len(tank_stats['missing']) + len(map_stats['missing'])
    total_size = tank_stats['total_size'] + map_stats['total_size']

    print(f"\nВсего изображений: {total_found}")
    print(f"Отсутствует: {total_missing}")
    print(f"Общий размер: {format_bytes(total_size)}")

    # Рекомендации
    print("\n" + "="*80)
    print("РЕКОМЕНДАЦИИ")
    print("="*80)

    total_large = len(tank_stats['large']) + len(map_stats['large'])
    if total_large > 0:
        print(f"\n💡 Найдено {total_large} файлов > 100KB")
        print("   Рекомендуется оптимизировать:")
        print("   python scripts/optimize_images_png.py --apply")
        print("   python scripts/convert_to_webp.py --apply")

    if total_missing > 0:
        print(f"\n⚠️  Отсутствует {total_missing} файлов")
        print("   Проверьте наличие файлов в static/style/images/wot/")

    print("\n✅ Анализ завершён!")


if __name__ == '__main__':
    main()
