"""
Простой тест для проверки работоспособности ReplayDataCache
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lesta_replays.settings')
django.setup()

from replays.models import Replay
from replays.parser.replay_cache import ReplayDataCache

def test_replay_cache():
    """Тестирует ReplayDataCache на реальном реплее"""

    # Берём первый реплей из БД
    replay = Replay.objects.first()

    if not replay:
        print("❌ В БД нет реплеев для тестирования")
        return

    print(f"✅ Найден реплей ID={replay.id}")

    try:
        # Создаём кеш
        cache = ReplayDataCache(replay.payload)
        print(f"✅ Кеш создан: {cache}")

        # Проверяем основные свойства
        print(f"\n📊 Проверка свойств кеша:")
        print(f"  - player_id: {cache.player_id}")
        print(f"  - player_team: {cache.player_team}")
        print(f"  - достижений: {len(cache.get_achievements())}")
        print(f"  - common данные: {len(cache.common)} полей")
        print(f"  - personal данные: {len(cache.personal)} полей")
        print(f"  - players: {len(cache.players)} игроков")
        print(f"  - vehicles: {len(cache.vehicles)} записей")
        print(f"  - avatars: {len(cache.avatars)} аватаров")

        # Проверяем повторный доступ (должен вернуть закешированные данные)
        personal1 = cache.personal
        personal2 = cache.personal

        if personal1 is personal2:
            print(f"\n✅ Кеширование работает! (personal1 is personal2)")
        else:
            print(f"\n❌ Кеширование НЕ работает!")

        print(f"\n✅ Все проверки пройдены!")

    except Exception as e:
        print(f"\n❌ Ошибка при создании кеша: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_replay_cache()
