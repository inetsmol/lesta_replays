"""
Тестовый скрипт для извлечения arenaUniqueID из файлов реплеев.
"""
import os
import sys
import django

# Настройка Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lesta_replays.settings')
django.setup()

from wotreplay.mtreplay import ReplayData
from replays.parser.parser import Parser
import json


def test_replay_file(file_path):
    """Тестирует различные способы извлечения arenaUniqueID из файла."""

    print(f"\n{'='*80}")
    print(f"Тестирование файла: {file_path}")
    print(f"{'='*80}\n")

    # Способ 1: Через ReplayData.battle_metadata
    print("=== Способ 1: ReplayData.battle_metadata ===")
    try:
        replay_data = ReplayData(file_path)
        metadata = replay_data.battle_metadata
        print(f"Тип metadata: {type(metadata)}")
        print(f"Длина metadata: {len(metadata) if metadata else 'None'}")

        if metadata and len(metadata) > 0:
            print(f"Тип metadata[0]: {type(metadata[0])}")
            print(f"Ключи metadata[0]: {list(metadata[0].keys())[:10] if isinstance(metadata[0], dict) else 'не dict'}")

            arena_id = metadata[0].get('arenaUniqueID') if isinstance(metadata[0], dict) else None
            print(f"arenaUniqueID: {arena_id}")
        else:
            print("metadata пустой или None")
    except Exception as e:
        print(f"ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

    # Способ 2: Через Parser (replays.parser.parser)
    print("\n=== Способ 2: Parser (replays.parser.parser) ===")
    try:
        parser = Parser(file_path)
        result = parser.parse()

        print(f"Тип result: {type(result)}")

        if isinstance(result, dict):
            print(f"Ключи верхнего уровня: {list(result.keys())}")

            # Ищем arenaUniqueID
            if 'arenaUniqueID' in result:
                print(f"arenaUniqueID найден в корне: {result['arenaUniqueID']}")

            # Проверяем вложенные структуры
            if 'metadata' in result:
                print(f"Найден ключ 'metadata', тип: {type(result['metadata'])}")
                if isinstance(result['metadata'], dict):
                    print(f"Ключи metadata: {list(result['metadata'].keys())[:10]}")
                    if 'arenaUniqueID' in result['metadata']:
                        print(f"arenaUniqueID в metadata: {result['metadata']['arenaUniqueID']}")

            # Проверяем payload
            if 'payload' in result:
                print(f"Найден ключ 'payload', тип: {type(result['payload'])}")
                payload = result['payload']

                if isinstance(payload, list) and len(payload) > 0:
                    print(f"payload[0] тип: {type(payload[0])}")
                    if isinstance(payload[0], dict):
                        print(f"Ключи payload[0]: {list(payload[0].keys())[:10]}")
                        if 'arenaUniqueID' in payload[0]:
                            print(f"arenaUniqueID в payload[0]: {payload[0]['arenaUniqueID']}")
                elif isinstance(payload, dict):
                    print(f"Ключи payload: {list(payload.keys())[:10]}")
                    if 'arenaUniqueID' in payload:
                        print(f"arenaUniqueID в payload: {payload['arenaUniqueID']}")

    except Exception as e:
        print(f"ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

    # Способ 3: Прямое чтение через Replay
    print("\n=== Способ 3: Через wotreplay.Replay ===")
    try:
        from wotreplay.action.extract_data_from_replay import Replay

        replay = Replay(file=file_path)

        # Проверяем доступные атрибуты и методы
        print(f"Атрибуты replay: {[attr for attr in dir(replay) if not attr.startswith('_')][:20]}")

        # Пробуем получить raw данные
        if hasattr(replay, 'replay_data'):
            print(f"\nТип replay.replay_data: {type(replay.replay_data)}")

            if isinstance(replay.replay_data, dict):
                print(f"Ключи replay_data: {list(replay.replay_data.keys())[:10]}")

                # Ищем arenaUniqueID
                if 'arenaUniqueID' in replay.replay_data:
                    print(f"arenaUniqueID найден: {replay.replay_data['arenaUniqueID']}")

                # Проверяем первый элемент если это список
                for key in replay.replay_data.keys():
                    val = replay.replay_data[key]
                    if isinstance(val, (list, dict)) and key in ['0', 0, 'metadata', 'data']:
                        print(f"\nКлюч '{key}', тип: {type(val)}")
                        if isinstance(val, list) and len(val) > 0:
                            print(f"  Элемент [0] тип: {type(val[0])}")
                            if isinstance(val[0], dict):
                                print(f"  Ключи [0]: {list(val[0].keys())[:10]}")
                                if 'arenaUniqueID' in val[0]:
                                    print(f"  arenaUniqueID в {key}[0]: {val[0]['arenaUniqueID']}")

    except Exception as e:
        print(f"ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    # Тестируем первые 2 файла
    test_files = [
        "media/07.10.2025 kv-3 aerodrom.mtreplay",
        "media/1010.mtreplay",
    ]

    for file_path in test_files:
        if os.path.exists(file_path):
            test_replay_file(file_path)
        else:
            print(f"Файл не найден: {file_path}")
