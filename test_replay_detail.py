"""
Тест для проверки работоспособности страницы деталей реплея
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lesta_replays.settings')
django.setup()

from django.test import RequestFactory
from replays.views import ReplayDetailView
from replays.models import Replay

def test_replay_detail_view():
    """Тестирует загрузку страницы деталей реплея"""

    # Берём реплей ID=41 (из ошибки)
    try:
        replay = Replay.objects.get(pk=41)
    except Replay.DoesNotExist:
        print("❌ Реплей ID=41 не найден, беру первый доступный")
        replay = Replay.objects.first()
        if not replay:
            print("❌ В БД нет реплеев для тестирования")
            return

    print(f"✅ Тестируем реплей ID={replay.id}")

    # Создаём фейковый request
    factory = RequestFactory()
    request = factory.get(f'/replays/{replay.id}/')

    # Создаём view
    view = ReplayDetailView()
    view.request = request
    view.kwargs = {'pk': replay.id}
    view.object = replay

    try:
        # Получаем контекст
        print(f"⏳ Получение контекста...")
        context = view.get_context_data()

        print(f"\n✅ Контекст успешно получен!")
        print(f"\n📊 Содержимое контекста:")
        print(f"  - replay: {context.get('replay')}")
        print(f"  - personal_data: {len(context.get('personal_data', {}))} полей")
        print(f"  - achievements_nonbattle: {context.get('achievements_nonbattle').count() if context.get('achievements_nonbattle') else 0}")
        print(f"  - achievements_battle: {context.get('achievements_battle').count() if context.get('achievements_battle') else 0}")
        print(f"  - team_results: {'✓' if context.get('team_results') else '✗'}")
        print(f"  - detailed_report: {'✓' if context.get('detailed_report') else '✗'}")
        print(f"  - interaction_rows: {len(context.get('interaction_rows', []))} строк")

        if 'parse_error' in context:
            print(f"\n⚠️  Ошибка парсинга: {context['parse_error']}")
        else:
            print(f"\n✅ Все данные успешно обработаны!")

    except Exception as e:
        print(f"\n❌ Ошибка при получении контекста: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_replay_detail_view()
