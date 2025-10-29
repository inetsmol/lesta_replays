# Оптимизация ExtractorV2 и ReplayDetailView

Документация по оптимизации обработки страницы деталей реплея.

## 📊 Результаты оптимизации

### Метрики производительности (Реплей ID=41, 30 игроков)

| Метрика | До | После | Улучшение |
|---------|-----|-------|-----------|
| **Время обработки** | 16.30 мс | **2.70 мс** | **↓ 83%** |
| **SQL запросов** | 16 | **3** | **↓ 81%** |
| **Парсинг JSON** | 10-15 раз | **1 раз** | **↓ 90+%** |

### Оставшиеся SQL запросы (все необходимые)

1. `SELECT * FROM replays_tank WHERE vehicleId IN (...)` - загрузка всех танков боя
2. `SELECT * FROM replays_achievement WHERE achievement_id IN (...)` - достижения игрока
3. `SELECT achievement_id, name FROM replays_achievement WHERE ...` - медали всех игроков

## 🏗️ Архитектура

### Компоненты системы

```
┌─────────────────────────────────────────────────────────────┐
│                    ReplayDetailView                          │
│  (replays/views.py)                                          │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
        ┌───────────────────────────────┐
        │   ЭТАП 1: Создание кеша       │
        │   ReplayDataCache(payload)    │
        │   • Парсинг JSON - 1 раз!     │
        │   • Ленивая загрузка свойств  │
        └───────────┬───────────────────┘
                    │
                    ▼
        ┌───────────────────────────────┐
        │   ЭТАП 2: Предзагрузка БД     │
        │   _preload_tanks(cache)       │
        │   _preload_achievements(cache)│
        │   • Batch loading - 2 запроса │
        └───────────┬───────────────────┘
                    │
                    ▼
        ┌───────────────────────────────┐
        │   ЭТАП 3: Извлечение данных   │
        │   ExtractorV2.методы(cache)   │
        │   • Использует кеш            │
        │   • Без повторных запросов    │
        └───────────────────────────────┘
```

### 1. ReplayDataCache (`replays/parser/replay_cache.py`)

**Назначение**: Кеширует часто используемые данные из JSON payload.

**Ключевые особенности:**
- Парсинг JSON выполняется **только один раз** при создании экземпляра
- Ленивая загрузка свойств через `@property`
- Кеширование всех обращений к данным

**API:**

```python
from replays.parser.replay_cache import ReplayDataCache

# Создание кеша
cache = ReplayDataCache(replay.payload)

# Доступ к данным (кешируются автоматически)
player_id = cache.player_id              # ID игрока
player_team = cache.player_team          # Команда игрока (1 или 2)
common = cache.common                    # Общие данные боя
personal = cache.personal                # Персональные данные
players = cache.players                  # Данные всех игроков
vehicles = cache.vehicles                # Данные техники
avatars = cache.avatars                  # Данные аватаров
achievements = cache.get_achievements()  # Список достижений
```

**Пример использования:**

```python
# ❌ СТАРЫЙ КОД (неэффективно)
payload = json.loads(replay.payload)  # Парсинг 1
personal = get_personal_by_player_id(payload)  # Парсинг 2
common = payload[1][0].get('common')  # Парсинг 3
players = payload[1][0].get('players')  # Парсинг 4
# ... 10+ повторных парсингов

# ✅ НОВЫЙ КОД (эффективно)
cache = ReplayDataCache(replay.payload)  # Парсинг 1 раз!
personal = cache.personal  # Кешированный доступ
common = cache.common      # Кешированный доступ
players = cache.players    # Кешированный доступ
```

### 2. ExtractorV2 (`replays/parser/extractor.py`)

**Назначение**: Извлекает и трансформирует данные из кеша для отображения.

**Оптимизированные методы:**

```python
# Минимальный набор персональных данных (3 поля вместо 60+)
get_personal_data_minimal(cache) -> dict

# Детали боя с использованием кеша
get_details_data(cache) -> dict

# Тип боя с мемоизацией
get_battle_type_label(cache) -> str

# Результат боя
get_battle_outcome(cache) -> dict

# Текст смерти с мемоизацией
get_death_text(cache) -> str

# Имя убийцы
get_killer_name(cache) -> str

# Детальный отчет
get_detailed_report(cache) -> dict

# Командные результаты с предзагруженными кешами
get_team_results(cache, tanks_cache) -> dict

# Взаимодействия (объединение двух методов в один проход)
build_interactions_data(cache, tanks_cache) -> tuple[list, dict]
```

**Мемоизация:**

Часто вызываемые справочные методы используют `@lru_cache`:

```python
from functools import lru_cache

@staticmethod
@lru_cache(maxsize=8)
def _death_reason_to_text(code: int) -> str:
    """Преобразует код причины смерти в текст"""
    ...

@staticmethod
@lru_cache(maxsize=32)
def _get_battle_type_by_gameplay_id(gameplay_id: str) -> Optional[str]:
    """Определяет тип боя по gameplay ID"""
    ...
```

### 3. ExtractorContext (`replays/parser/extractor.py`)

**Назначение**: Кеширует промежуточные вычисления внутри экстрактора.

```python
from replays.parser.extractor import ExtractorContext

# Создание контекста
context = ExtractorContext(cache)

# Кеширование вычисленных значений
context.cache_value("net_income", net_income)
value = context.get_cached("net_income")
```

### 4. ReplayDetailView (`replays/views.py`)

**Оптимизированный процесс:**

```python
def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)

    # ============================================================
    # ЭТАП 1: СОЗДАНИЕ КЕША (парсинг JSON один раз!)
    # ============================================================
    cache = ReplayDataCache(self.object.payload)

    # ============================================================
    # ЭТАП 2: ПРЕДЗАГРУЗКА ДАННЫХ (минимум запросов к БД)
    # ============================================================
    tanks_cache = self._preload_tanks(cache)  # 1 SQL запрос
    achievements_nonbattle, achievements_battle = self._preload_achievements(cache)  # 1 SQL запрос

    # Создаём контекст для кеширования промежуточных вычислений
    extractor_context = ExtractorContext(cache)

    # ============================================================
    # ЭТАП 3: ИЗВЛЕЧЕНИЕ ДАННЫХ (с использованием кеша)
    # ============================================================
    context['personal_data'] = ExtractorV2.get_personal_data_minimal(cache)
    context['details'] = ExtractorV2.get_details_data(cache)
    context['team_results'] = ExtractorV2.get_team_results(cache, tanks_cache)
    context['battle_outcome'] = ExtractorV2.get_battle_outcome(cache)
    # ... остальные методы

    return context
```

## 💡 Ключевые принципы оптимизации

### 1. Кеширование данных

**Проблема:** Повторный парсинг JSON payload при каждом обращении к данным.

**Решение:** ReplayDataCache с ленивой загрузкой.

```python
# Плохо: парсинг при каждом обращении
def get_data():
    payload = json.loads(replay_json)  # Парсинг!
    return payload[1][0]['personal']

# Хорошо: парсинг один раз, кеширование навсегда
cache = ReplayDataCache(replay_json)  # Парсинг 1 раз
data1 = cache.personal  # Из кеша
data2 = cache.personal  # Из кеша (те же объекты!)
```

### 2. Batch Loading (пакетная загрузка)

**Проблема:** N+1 запросы к БД (загрузка каждого танка отдельным запросом).

**Решение:** Предзагрузка всех танков одним запросом.

```python
# Плохо: N+1 запросы
for avatar_id, data in avatars.items():
    vehicle_tag = extract_tag(data['vehicleType'])
    tank = Tank.objects.get(vehicleId=vehicle_tag)  # SQL запрос!

# Хорошо: 1 запрос для всех танков
tank_tags = {extract_tag(d['vehicleType']) for d in avatars.values()}
tanks = Tank.objects.filter(vehicleId__in=tank_tags)  # 1 SQL запрос!
tanks_cache = {t.vehicleId: t for t in tanks}

for avatar_id, data in avatars.items():
    vehicle_tag = extract_tag(data['vehicleType'])
    tank = tanks_cache.get(vehicle_tag)  # Из кеша!
```

### 3. Материализация QuerySet

**Проблема:** Повторные `.count()` вызовы на QuerySet генерируют дополнительные SQL запросы.

**Решение:** Конвертация QuerySet в список.

```python
# Плохо: каждый .count() = SQL запрос
achievements = Achievement.objects.filter(...)
count1 = achievements.count()  # SQL!
count2 = achievements.count()  # SQL!

# Хорошо: конвертируем в список
achievements = list(Achievement.objects.filter(...))  # 1 SQL запрос
count1 = len(achievements)  # В памяти
count2 = len(achievements)  # В памяти
```

### 4. Мемоизация справочных функций

**Проблема:** Повторные вызовы функций преобразования с одними и теми же параметрами.

**Решение:** `@lru_cache` для кеширования результатов.

```python
from functools import lru_cache

# Без мемоизации: вычисляется каждый раз
def get_battle_type(gameplay_id):
    mapping = {...}  # Большой словарь
    return mapping.get(gameplay_id)

# С мемоизацией: вычисляется один раз для каждого уникального ID
@lru_cache(maxsize=32)
def get_battle_type(gameplay_id):
    mapping = {...}
    return mapping.get(gameplay_id)
```

### 5. Минимизация копирования данных

**Проблема:** Копирование 60+ полей, из которых используется ~20%.

**Решение:** Возврат только необходимых полей.

```python
# Плохо: копируем все 60+ полей
def get_personal_data(payload):
    personal = get_full_personal(payload)
    return personal  # 60+ полей!

# Хорошо: возвращаем только используемые поля
def get_personal_data_minimal(cache):
    p = cache.personal
    return {
        'credits': int(p.get('credits', 0)),
        'xp': int(p.get('xp', 0)),
        'crystal': int(p.get('crystal', 0))
    }  # Только 3 поля!
```

## 🔧 Использование

### Добавление нового метода экстрактора

```python
@staticmethod
def get_new_data(cache: 'ReplayDataCache') -> dict:
    """
    Новый метод для извлечения данных.

    Args:
        cache: ReplayDataCache с данными реплея

    Returns:
        Словарь с извлеченными данными
    """
    # Используем кеш, а не payload!
    personal = cache.personal
    common = cache.common

    return {
        'field1': personal.get('value1'),
        'field2': common.get('value2'),
    }
```

### Вызов в View

```python
def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)

    # Создаем кеш
    cache = ReplayDataCache(self.object.payload)

    # Вызываем метод с кешем
    context['new_data'] = ExtractorV2.get_new_data(cache)

    return context
```

## 🛠️ Инструменты профилирования

### 1. Бенчмарк (быстрая проверка)

```bash
python scripts/benchmark_replay_detail.py <replay_id> [runs]

# Пример
python scripts/benchmark_replay_detail.py 41 10
```

**Вывод:**
- Среднее/минимальное/максимальное время выполнения
- Количество SQL запросов
- Типы SQL запросов

### 2. Детальное профилирование

```bash
python scripts/profile_replay_detail.py <replay_id> [runs]

# Пример
python scripts/profile_replay_detail.py 41 3
```

**Вывод:**
- ТОП-30 функций по cumulative time
- ТОП-30 функций по total time
- ТОП-20 функций по количеству вызовов

### 3. Анализ SQL запросов

```bash
python scripts/analyze_queries.py <replay_id>

# Пример
python scripts/analyze_queries.py 41
```

**Вывод:**
- Полный список всех SQL запросов
- Группировка по типам
- Обнаружение дублирующихся запросов

## 📈 Метрики успеха

### Достигнутые показатели

✅ **Время обработки:** 2.70 мс (цель: < 250 мс)
✅ **SQL запросов:** 3 (цель: 3-5)
✅ **Парсинг JSON:** 1 раз (цель: 1 раз)

### Мониторинг производительности

Для контроля производительности в production:

1. **Django Debug Toolbar** (dev only):
   ```python
   # settings.py (только для DEBUG=True)
   INSTALLED_APPS += ['debug_toolbar']
   ```

2. **Sentry Performance Monitoring**:
   - Уже настроен в проекте
   - Отслеживает медленные запросы и views

3. **Custom middleware** (опционально):
   ```python
   import time
   import logging

   logger = logging.getLogger(__name__)

   class PerformanceMiddleware:
       def __init__(self, get_response):
           self.get_response = get_response

       def __call__(self, request):
           start = time.perf_counter()
           response = self.get_response(request)
           elapsed = (time.perf_counter() - start) * 1000

           if elapsed > 100:  # Предупреждение если > 100ms
               logger.warning(f"Slow request: {request.path} took {elapsed:.2f}ms")

           return response
   ```

## 🧪 Тестирование

### Unit-тесты

Созданы тесты для проверки корректности оптимизаций:

```bash
# Тесты для ReplayDataCache (18 тестов)
python manage.py test replays.tests.test_replay_cache

# Тесты для ExtractorV2 (15 тестов)
python manage.py test replays.tests.test_extractor_optimized

# Все тесты
python manage.py test replays.tests
```

### Ручное тестирование

1. Откройте страницу деталей реплея: `/replays/<id>/`
2. Проверьте DevTools → Network → количество запросов
3. Проверьте Console → нет ошибок JavaScript
4. Проверьте корректность отображения всех данных

## 📚 Дополнительные ресурсы

- [OPTIMIZATION_PLAN.md](../OPTIMIZATION_PLAN.md) - полный план оптимизации
- [CLAUDE.md](../CLAUDE.md) - общая документация проекта
- Django Query Optimization: https://docs.djangoproject.com/en/5.2/topics/db/optimization/
- Python functools.lru_cache: https://docs.python.org/3/library/functools.html#functools.lru_cache

## 🔄 История изменений

### 2025-01 - Полная оптимизация (Этапы 1-5)

**Изменения:**
- Создан `ReplayDataCache` для кеширования JSON парсинга
- Добавлены методы предзагрузки `_preload_tanks()` и `_preload_achievements()`
- Оптимизированы все методы ExtractorV2 для работы с кешем
- Добавлена мемоизация для справочных функций
- Удалены устаревшие методы `get_player_interactions()` и `_avatar_info()`
- Материализованы QuerySet достижений

**Результат:**
- Время обработки: ↓ 83% (с 16.30 мс до 2.70 мс)
- SQL запросов: ↓ 81% (с 16 до 3)
- Парсинг JSON: ↓ 90% (с 10-15 раз до 1 раза)

---

**Автор:** Claude Code
**Дата:** 2025-01
**Версия:** 1.0
