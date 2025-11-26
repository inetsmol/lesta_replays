#!/usr/bin/env python
"""
Скрипт для извлечения arenaUniqueID и playerName из всех файлов реплеев.

Перебирает все .mtreplay файлы в папке media, извлекает из них:
- arenaUniqueID
- playerName

Сохраняет результаты в JSON файл.

Использование:
    python scripts/extract_arena_and_player.py
    python scripts/extract_arena_and_player.py --output results.json
    python scripts/extract_arena_and_player.py --workers 8  # Количество потоков
"""
import sys
import os
import json
from pathlib import Path
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Настраиваем Django для доступа к моделям
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lesta_replays.settings")
import django
django.setup()

from replays.parser.parser import Parser, ParseError


def extract_replay_data(file_path: Path) -> dict:
    """
    Извлекает arenaUniqueID и playerName из файла реплея.

    Args:
        file_path: Путь к файлу реплея

    Returns:
        Словарь с данными или информацией об ошибке
    """
    try:
        # Читаем файл в байты
        file_content = file_path.read_bytes()

        # Парсим используя Parser из replays
        parser = Parser()
        data = parser.parse_bytes(file_content)

        # data - это JSON строка вида "[{...}, [...]]"
        # Распарсим её, чтобы получить структуру
        parsed_data = json.loads(data)

        if not isinstance(parsed_data, list) or len(parsed_data) < 1:
            return {
                'filename': file_path.name,
                'arenaUniqueID': None,
                'playerName': None,
                'status': 'error',
                'error': 'Invalid payload structure'
            }

        # Первый элемент - метаданные (dict)
        metadata = parsed_data[0]

        arena_unique_id = metadata.get('arenaUniqueID')
        player_name = metadata.get('playerName')

        return {
            'filename': file_path.name,
            'arenaUniqueID': arena_unique_id,
            'playerName': player_name,
            'status': 'success'
        }
    except ParseError as e:
        # ParseError означает, что файл не содержит статистику боя
        return {
            'filename': file_path.name,
            'arenaUniqueID': None,
            'playerName': None,
            'status': 'error',
            'error': f'ParseError: {str(e)}'
        }
    except Exception as e:
        return {
            'filename': file_path.name,
            'arenaUniqueID': None,
            'playerName': None,
            'status': 'error',
            'error': str(e)
        }


def process_batch(files_batch):
    """
    Обрабатывает пакет файлов в одном потоке.

    Args:
        files_batch: Список файлов для обработки

    Returns:
        Словарь с результатами обработки
    """
    results = {}

    for file_path in files_batch:
        data = extract_replay_data(file_path)
        filename = data.pop('filename')
        results[filename] = data

    return results


def main():
    """Главная функция."""
    parser = argparse.ArgumentParser(description='Извлечение arenaUniqueID и playerName из реплеев')
    parser.add_argument('--output', '-o',
                       default='replay_arena_player_data.json',
                       help='Имя файла для сохранения результатов (по умолчанию: replay_arena_player_data.json)')
    parser.add_argument('--media-dir', '-m',
                       default=None,
                       help='Путь к папке с реплеями (по умолчанию: media из настроек Django)')
    parser.add_argument('--workers', '-w',
                       type=int,
                       default=4,
                       help='Количество потоков для обработки (по умолчанию: 4)')

    args = parser.parse_args()

    print("=" * 80)
    print("ИЗВЛЕЧЕНИЕ ДАННЫХ ИЗ ФАЙЛОВ РЕПЛЕЕВ")
    print("=" * 80)

    # Определяем папку с реплеями
    if args.media_dir:
        media_dir = Path(args.media_dir)
    else:
        # Используем папку media из проекта
        media_dir = project_root / 'media'

    if not media_dir.exists():
        print(f"\n❌ Папка {media_dir} не существует!")
        return 1

    print(f"\nПапка с реплеями: {media_dir}")
    print(f"Потоков для обработки: {args.workers}")

    # Ищем все .mtreplay файлы
    print("\nПоиск файлов .mtreplay...")
    replay_files = list(media_dir.glob('**/*.mtreplay'))
    total_count = len(replay_files)

    if total_count == 0:
        print(f"\n❌ Не найдено файлов .mtreplay в папке {media_dir}")
        return 1

    print(f"Найдено файлов: {total_count}")

    # Разбиваем файлы на пакеты для параллельной обработки
    batch_size = max(1, total_count // args.workers)
    batches = [replay_files[i:i + batch_size] for i in range(0, total_count, batch_size)]

    print(f"Размер пакета: ~{batch_size} файлов")
    print(f"Количество пакетов: {len(batches)}")

    # Обрабатываем файлы параллельно
    print("\nОбработка файлов...")
    output_data = {}
    success_count = 0
    error_count = 0
    processed_count = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Запускаем обработку пакетов
        future_to_batch = {
            executor.submit(process_batch, batch): i
            for i, batch in enumerate(batches)
        }

        # Собираем результаты по мере завершения
        for future in as_completed(future_to_batch):
            batch_results = future.result()
            output_data.update(batch_results)

            # Обновляем счетчики
            for data in batch_results.values():
                if data['status'] == 'success':
                    success_count += 1
                else:
                    error_count += 1

            processed_count += len(batch_results)
            print(f"Обработано: {processed_count}/{total_count} ({processed_count/total_count*100:.1f}%)", end='\r')

    print(f"\nОбработка: {total_count}/{total_count} (100.0%)")

    # Сохраняем результаты
    output_file = project_root / args.output
    print(f"\nСохранение результатов в {output_file}...")

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    # Вывод статистики
    print("\n" + "=" * 80)
    print("РЕЗУЛЬТАТЫ")
    print("=" * 80)
    print(f"Всего файлов:       {total_count}")
    print(f"Успешно обработано: {success_count}")
    print(f"Ошибки:             {error_count}")
    print(f"\nРезультаты сохранены в: {output_file}")

    # Показываем примеры ошибок
    if error_count > 0:
        print("\n" + "-" * 80)
        print("ПРИМЕРЫ ОШИБОК (первые 5):")
        print("-" * 80)
        error_examples = [(filename, data) for filename, data in output_data.items() if data['status'] == 'error'][:5]
        for filename, err in error_examples:
            print(f"\nФайл: {filename}")
            print(f"Ошибка: {err['error']}")

    # Показываем примеры успешных данных
    if success_count > 0:
        print("\n" + "-" * 80)
        print("ПРИМЕРЫ УСПЕШНО ИЗВЛЕЧЕННЫХ ДАННЫХ (первые 3):")
        print("-" * 80)
        success_examples = [(filename, data) for filename, data in output_data.items() if data['status'] == 'success'][:3]
        for filename, data in success_examples:
            print(f"\nФайл: {filename}")
            print(f"arenaUniqueID: {data['arenaUniqueID']}")
            print(f"playerName: {data['playerName']}")

    print("\n" + "=" * 80)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
