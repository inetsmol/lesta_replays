"""
Скрипт для извлечения arenaUniqueID из всех файлов реплеев и проверки на дубликаты.
"""
import os
import sys
from pathlib import Path
from collections import defaultdict

# Настройка Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lesta_replays.settings')

import django
django.setup()

from django.conf import settings
from wotreplay.action.extract_data_from_replay import Replay


def get_arena_id_from_file(file_path):
    """
    Извлекает arenaUniqueID из файла реплея.

    Returns:
        int или None: arenaUniqueID или None если не удалось извлечь
    """
    try:
        replay = Replay(file=str(file_path))
        arena_unique_id = replay.replay_data.get('arenaUniqueID')
        return arena_unique_id
    except Exception as e:
        print(f"Ошибка парсинга {Path(file_path).name}: {e}")
        return None


def scan_all_replays():
    """
    Сканирует все файлы реплеев и создает индекс по arenaUniqueID.

    Returns:
        tuple: (arena_index, errors, total_files)
            - arena_index: dict {arenaUniqueID: [список путей к файлам]}
            - errors: количество ошибок парсинга
            - total_files: общее количество обработанных файлов
    """
    media_root = Path(settings.MEDIA_ROOT)
    arena_index = defaultdict(list)
    errors = 0

    # Поиск всех .mtreplay файлов
    replay_files = list(media_root.rglob("*.mtreplay"))
    total = len(replay_files)

    print(f"Найдено файлов .mtreplay: {total}")
    print(f"Начинаю обработку...\n")

    for idx, file_path in enumerate(replay_files, 1):
        # Прогресс каждые 100 файлов
        if idx % 100 == 0 or idx == total:
            print(f"  Обработка файла {idx}/{total}...", end='\r')

        arena_id = get_arena_id_from_file(file_path)

        if arena_id is not None:
            arena_index[arena_id].append(str(file_path))
        else:
            errors += 1

    print(f"\n\nОбработка завершена!")

    return dict(arena_index), errors, total


def analyze_duplicates(arena_index):
    """
    Анализирует индекс на наличие дубликатов.

    Args:
        arena_index: dict {arenaUniqueID: [список путей к файлам]}

    Returns:
        dict: статистика дубликатов
    """
    duplicates = {}

    for arena_id, file_paths in arena_index.items():
        if len(file_paths) > 1:
            duplicates[arena_id] = file_paths

    return duplicates


def print_results(arena_index, errors, total_files):
    """
    Выводит результаты анализа.
    """
    print("\n" + "="*80)
    print("СТАТИСТИКА")
    print("="*80)
    print(f"Всего файлов обработано: {total_files}")
    print(f"Успешно распарсено: {total_files - errors}")
    print(f"Ошибок парсинга: {errors}")
    print(f"Уникальных arenaUniqueID: {len(arena_index)}")

    # Проверка на дубликаты
    duplicates = analyze_duplicates(arena_index)

    print(f"\n{'='*80}")
    print("ПРОВЕРКА НА ДУБЛИКАТЫ")
    print("="*80)

    if duplicates:
        print(f"Найдено arenaUniqueID с дубликатами: {len(duplicates)}")
        print(f"\nДетали дубликатов:\n")

        for arena_id, file_paths in sorted(duplicates.items()):
            print(f"arenaUniqueID: {arena_id}")
            print(f"  Количество файлов: {len(file_paths)}")

            for file_path in file_paths:
                file_name = Path(file_path).name
                print(f"    - {file_name}")
            print()

        # Статистика по количеству дубликатов
        duplicate_counts = defaultdict(int)
        for file_paths in duplicates.values():
            duplicate_counts[len(file_paths)] += 1

        print(f"{'='*80}")
        print("СТАТИСТИКА ДУБЛИКАТОВ ПО КОЛИЧЕСТВУ")
        print("="*80)
        for count in sorted(duplicate_counts.keys()):
            num_arenas = duplicate_counts[count]
            total_extra_files = num_arenas * (count - 1)
            print(f"{count} файла с одинаковым arenaUniqueID: {num_arenas} случаев ({total_extra_files} избыточных файлов)")

        total_duplicates = sum(len(files) - 1 for files in duplicates.values())
        print(f"\nВсего избыточных файлов: {total_duplicates}")

    else:
        print("✓ Дубликатов не найдено! Все arenaUniqueID уникальны.")

    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    print("="*80)
    print("ПРОВЕРКА arenaUniqueID НА ДУБЛИКАТЫ")
    print("="*80)
    print()

    # Сканируем все файлы
    arena_index, errors, total_files = scan_all_replays()

    # Выводим результаты
    print_results(arena_index, errors, total_files)
