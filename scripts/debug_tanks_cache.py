#!/usr/bin/env python
"""
Скрипт для отладки tanks_cache.
"""

import os
import sys
import django
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lesta_replays.settings')
django.setup()

from replays.models import Replay, Tank
from replays.parser.replay_cache import ReplayDataCache


def debug_tanks_cache(replay_id: int):
    try:
        replay = Replay.objects.get(pk=replay_id)
    except Replay.DoesNotExist:
        print(f"❌ Реплей с ID {replay_id} не найден")
        return

    print(f"🔍 Отладка tanks_cache для реплея ID={replay_id}\n")

    # Создаем кеш
    cache = ReplayDataCache(replay.payload)

    # Собираем все vehicleId из реплея (как в _preload_tanks)
    tank_tags = set()

    # Танк владельца реплея
    player_vehicle = cache.first_block.get("playerVehicle")
    if player_vehicle and ":" in player_vehicle:
        _, tag = player_vehicle.split(":", 1)
        tank_tags.add(tag)
        print(f"📌 Танк владельца: {player_vehicle} -> tag: {tag}")

    # Танки всех участников боя
    print(f"\n📌 Танки участников боя:")
    for avatar_id, avatar_data in cache.avatars.items():
        if isinstance(avatar_data, dict):
            vehicle_type = avatar_data.get("vehicleType", "")
            if ":" in vehicle_type:
                _, tag = vehicle_type.split(":", 1)
                tank_tags.add(tag)
                print(f"   Avatar {avatar_id}: {vehicle_type} -> tag: {tag}")

    print(f"\n📊 Всего уникальных тегов танков: {len(tank_tags)}")
    print(f"   Теги: {sorted(tank_tags)}")

    # Загружаем танки из БД
    tanks = Tank.objects.filter(vehicleId__in=tank_tags)
    tanks_cache = {t.vehicleId: t for t in tanks}

    print(f"\n📦 Загружено танков из БД: {len(tanks_cache)}")
    print(f"   vehicleId в кеше: {sorted(tanks_cache.keys())}")

    # Проверяем, все ли теги найдены
    missing_tags = tank_tags - set(tanks_cache.keys())
    if missing_tags:
        print(f"\n⚠️  НЕ НАЙДЕНЫ В БД: {sorted(missing_tags)}")
    else:
        print(f"\n✅ Все танки найдены в БД")

    # Теперь проверяем, что используется в extractor
    print(f"\n🔎 Проверка использования в _build_player_data:")

    raw = cache.avatars
    vehicles_stats = cache.vehicles

    for avatar_id in list(raw.keys())[:3]:  # Берем первые 3 для примера
        avatar_data = raw.get(avatar_id, {})
        vehicle_type = str(avatar_data.get("vehicleType", ""))

        if ":" in vehicle_type:
            vehicle_nation, vehicle_tag = vehicle_type.split(":", 1)
        else:
            vehicle_nation, vehicle_tag = "", vehicle_type

        print(f"\n   Avatar {avatar_id}:")
        print(f"      vehicle_type: {vehicle_type}")
        print(f"      vehicle_tag: {vehicle_tag}")
        print(f"      Найден в tanks_cache: {vehicle_tag in tanks_cache}")

        if vehicle_tag in tanks_cache:
            tank = tanks_cache[vehicle_tag]
            print(f"      Танк: {tank.name} (level {tank.level})")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("❌ Использование: python scripts/debug_tanks_cache.py <replay_id>")
        sys.exit(1)

    try:
        replay_id = int(sys.argv[1])
    except ValueError:
        print(f"❌ Некорректный ID реплея: {sys.argv[1]}")
        sys.exit(1)

    debug_tanks_cache(replay_id)
