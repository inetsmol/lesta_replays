#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wotreplay.settings')
django.setup()

from replays.models import Replay
from replays.parser.replay_cache import ReplayDataCache

replay = Replay.objects.get(pk=69)
cache = ReplayDataCache(replay.payload)

print("Player ID (owner):", cache.player_id)
print("Type:", type(cache.player_id))
print("\nVehicles keys:")
for key in list(cache.vehicles.keys())[:5]:  # Показываем первые 5
    print(f"  {key} (type: {type(key).__name__})")

print("\nAchievements with values from dossierLogRecords:")
ach_with_vals = cache.get_achievements_with_values()
for aid, val in ach_with_vals.items():
    print(f"  {aid}: {val}")
    if aid == 41:
        print(f"    ^ This is Medal Kay with degree {val}!")

# Проверим, есть ли владелец в vehicles
owner_id_str = str(cache.player_id)
print(f"\nLooking for owner with avatar_id: {owner_id_str}")
if owner_id_str in cache.vehicles:
    print(f"  ✓ Found in vehicles")
    vstats_list = cache.vehicles[owner_id_str]
    if isinstance(vstats_list, list) and vstats_list:
        vstats = vstats_list[0]
        print(f"  Achievements from vehicles: {vstats.get('achievements', [])}")
else:
    print(f"  ✗ NOT found in vehicles")
    print(f"  Available keys: {list(cache.vehicles.keys())[:10]}")
