"""Скрипт для поиска информации об отметках на стволе в payload реплея."""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wotreplay_site.settings')
django.setup()

from replays.models import Replay
import json


def find_fields_with_keyword(obj, keywords, path='', depth=0, max_depth=15):
    """Рекурсивный поиск полей содержащих keywords в названии."""
    results = []

    if depth > max_depth:
        return results

    if isinstance(obj, dict):
        for key, value in obj.items():
            key_lower = str(key).lower()

            # Проверяем совпадение с любым из keywords
            if any(kw in key_lower for kw in keywords):
                value_str = str(value)[:200] if not isinstance(value, (dict, list)) else f"{type(value).__name__} with {len(value)} items"
                results.append({
                    'path': f'{path}.{key}' if path else key,
                    'type': type(value).__name__,
                    'value': value_str,
                    'full_value': value
                })

            # Рекурсивно ищем в вложенных структурах
            if isinstance(value, (dict, list)):
                new_path = f'{path}.{key}' if path else str(key)
                results.extend(find_fields_with_keyword(value, keywords, new_path, depth + 1, max_depth))

    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            new_path = f'{path}[{i}]'
            results.extend(find_fields_with_keyword(item, keywords, new_path, depth + 1, max_depth))

    return results


if __name__ == '__main__':
    # Получаем первый реплей
    replay = Replay.objects.first()

    if not replay:
        print("No replays found in database")
        exit(1)

    print(f"Analyzing Replay ID: {replay.id}")
    print(f"Tank: {replay.tank}")
    print(f"Owner: {replay.owner}")
    print(f"Battle date: {replay.battle_date}")
    print("=" * 80)

    # Ищем поля связанные с отметками
    keywords = ['mark', 'mastery', 'excellence', 'moe']
    marks_fields = find_fields_with_keyword(replay.payload, keywords)

    print(f"\nFound {len(marks_fields)} fields containing: {', '.join(keywords)}")
    print("=" * 80)

    # Группируем по типу пути
    personal_fields = [f for f in marks_fields if 'personal' in f['path']]
    vehicle_fields = [f for f in marks_fields if 'vehicle' in f['path'].lower()]
    other_fields = [f for f in marks_fields if f not in personal_fields and f not in vehicle_fields]

    print("\n📊 PERSONAL FIELDS (владелец реплея):")
    print("-" * 80)
    for field in personal_fields[:10]:
        print(f"Path: {field['path']}")
        print(f"Type: {field['type']}")
        print(f"Value: {field['value']}")
        print()

    print("\n🚗 VEHICLE FIELDS (все участники):")
    print("-" * 80)
    for field in vehicle_fields[:10]:
        print(f"Path: {field['path']}")
        print(f"Type: {field['type']}")
        print(f"Value: {field['value']}")
        print()

    print("\n🔍 OTHER FIELDS:")
    print("-" * 80)
    for field in other_fields[:10]:
        print(f"Path: {field['path']}")
        print(f"Type: {field['type']}")
        print(f"Value: {field['value']}")
        print()

    # Детальный анализ markOfMastery
    print("\n" + "=" * 80)
    print("DETAILED ANALYSIS: markOfMastery")
    print("=" * 80)

    moe_fields = [f for f in marks_fields if 'markofmastery' in f['path'].lower()]
    for field in moe_fields:
        print(f"\nPath: {field['path']}")
        print(f"Type: {field['type']}")
        print(f"Value: {field['full_value']}")

        # Если это число, расшифровываем значение
        if isinstance(field['full_value'], int):
            moe_names = {
                0: "Нет отметки",
                1: "3-я отметка (65%)",
                2: "2-я отметка (85%)",
                3: "1-я отметка (95%)",
                4: "Мастер (100%)"
            }
            print(f"Meaning: {moe_names.get(field['full_value'], 'Unknown')}")

    # Ищем процент урона (может быть отдельное поле)
    print("\n" + "=" * 80)
    print("SEARCHING FOR DAMAGE RATING / PERCENTAGE:")
    print("=" * 80)

    damage_keywords = ['rating', 'damagerating', 'percent', 'achievement']
    damage_fields = find_fields_with_keyword(replay.payload, damage_keywords, max_depth=10)

    # Фильтруем только числовые поля в разумном диапазоне (0-100 или 0-10000)
    potential_moe_fields = []
    for field in damage_fields:
        if isinstance(field['full_value'], (int, float)):
            value = field['full_value']
            # Процент МОЕ обычно в диапазоне 0-100 или 0-10000 (в сотых долях)
            if (0 <= value <= 100) or (0 <= value <= 10000):
                potential_moe_fields.append(field)

    print(f"\nFound {len(potential_moe_fields)} potential MoE percentage fields:")
    for field in potential_moe_fields[:20]:
        print(f"{field['path']}: {field['full_value']}")
