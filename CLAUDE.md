# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Communication Language

**ВАЖНО**: Всегда общайтесь с пользователем ТОЛЬКО на русском языке. Все ответы, объяснения и комментарии должны быть на русском.

**IMPORTANT**: Always communicate with the user ONLY in Russian. All responses, explanations, and comments must be in Russian.

## Project Overview

Django web application for uploading, parsing, and displaying World of Tanks game replays (.mtreplay files). Users can upload replay files, which are parsed to extract detailed battle statistics, and browse replays with advanced filtering and sorting capabilities.

## Tech Stack

- **Backend**: Django 5.2.6, Python 3.12
- **Database**: SQLite (dev) / PostgreSQL (production)
- **Auth**: django-allauth with Google/Yandex OAuth
- **Comments**: django-comments-xtd
- **Monitoring**: Sentry
- **Server**: Gunicorn + WhiteNoise (static files)
- **Frontend**: Vanilla JavaScript, jQuery 3.7.1, custom CSS
- **Deployment**: Docker + docker-compose

## Architecture

### Core Components

**replays/** - Main Django app
- `models.py`: Core models (Replay, Tank, Player, Achievement, Map)
- `views.py`: Class-based views for replay handling (ОПТИМИЗИРОВАНО - см. [Performance Optimization](#performance-optimization))
- `services.py`: Business logic services (ReplayProcessingService, FileStorageService, etc.)
- `parser/`: Replay file parsing logic
  - `parser.py`: Main Parser class for .mtreplay files
  - `extractor.py`: ExtractorV2 class for extracting structured data (ОПТИМИЗИРОВАНО)
  - `extractor_reusable.py`: ExtractorWithReusableInfo для работы с client_adapter (НОВОЕ)
  - `replay_cache.py`: ReplayDataCache для кеширования JSON данных (НОВОЕ)
  - `parsers.py`: Low-level binary parsing utilities
  - `client_adapter/`: Портированные модули из клиентского кода battle_results (НОВОЕ)
    - `adapter.py`: ReplayDataAdapter - интеграция с Django парсером
    - `reusable_info.py`: ReusableInfo - главный контейнер данных боя
    - `common.py`, `personal.py`, `players.py`, `vehicles.py`, `avatars.py`: Info классы
    - `constants.py`: ARENA_BONUS_TYPE, PLAYER_TEAM_RESULT и другие константы
- `error_handlers.py`: Centralized error handling for replay uploads
- `validators.py`: File and batch upload validation
- `tests/`: Unit-тесты для оптимизированных компонентов (НОВОЕ)
  - `test_client_adapter_*.py`: 199 тестов для client_adapter модулей
  - `test_extractor_reusable.py`: 41 тест для ExtractorWithReusableInfo

**wotreplay/** - Standalone replay parsing package
- `mtreplay.py`: ReplayData facade class
- `action/`: Extract data from replay files
- `orm/`: Data models for replay structure
- `utils/`: File handling and utilities

**Separation of Concerns**:
- Parser (`wotreplay/`) is isolated from Django - pure Python binary file parsing
- Services layer (`replays/services.py`) handles business logic, keeping views thin
- ExtractorV2 (`replays/parser/extractor.py`) transforms raw parsed data into Django-ready structures
- client_adapter (`replays/parser/client_adapter/`) provides validated access to battle results data
- ExtractorWithReusableInfo (`replays/parser/extractor_reusable.py`) provides extended battle type analysis

### Key Models & Relationships

```
User (Django auth)
  └─> Replay.user (uploader)

Player (game player)
  └─> Replay.owner (player who recorded the battle)
  └─> Replay.participants (M2M - all battle participants)

Tank
  └─> Replay.tank (vehicle used in battle)

Map
  └─> Replay.map (battle location)
```

**Important**: Replay has BOTH `user` (site user who uploaded) and `owner` (game player who recorded it). These are different entities.

### Replay Data Structure (battle_result.json)

**КРИТИЧНО:** Структура JSON данных реплея имеет контринтуитивные особенности!

**Структура файла:**

```text
[0] METADATA                     - Метаданные реплея (16 полей)
[1] BATTLE_DATA (массив из 3)
    ├─ [0] BATTLE_RESULTS        - Детальные результаты боя ✅ ОСНОВНОЕ
    │   ├─ common (18 полей)     - общие данные боя
    │   ├─ personal.avatar (83)  - статистика владельца
    │   ├─ players (30)          - информация об игроках
    │   ├─ avatars (30)          - краткая статистика
    │   └─ vehicles (30)         - детальная статистика (~80 полей)
    ├─ [1] EXTENDED_VEHICLE_INFO - дубликат data[0].vehicles ⚠️
    └─ [2] FRAGS                 - дубликат vehicles.kills ⚠️
```

**⚠️ КРИТИЧЕСКАЯ ОСОБЕННОСТЬ: Контринтуитивная логика имен!**

Поля `name`, `fakeName`, `realName` имеют **ПРОТИВОПОЛОЖНЫЙ смысл** в разных секциях:

**В `data[0].vehicles`:**

- `name` = НАСТОЯЩЕЕ имя игрока
- `fakeName` = имя В БОЮ (анонимное, если включено)

**В `data[1][0].players`:**

- `name` = имя В БОЮ (анонимное, если включено)
- `realName` = НАСТОЯЩЕЕ имя игрока

**Правильное использование:**

- Имя в бою: `vehicles[session]['fakeName']` или `players[id]['name']`
- Настоящее имя: `vehicles[session]['name']` или `players[id]['realName']`

**Важные особенности:**

1. `data[1][0].vehicles[session_id]` - это **СПИСОК** из 1 элемента, не dict!

   ```python
   # Правильно:
   kills = data[1][0]['vehicles'][session_id][0]['kills']
   # Неправильно:
   kills = data[1][0]['vehicles'][session_id]['kills']  # TypeError!
   ```

2. Два типа ID:
   - `avatarSessionID` - временный ID сессии (используется в vehicles)
   - `accountDBID` - постоянный ID игрока (используется в players, avatars)

3. `data[1][1]` и `data[1][2]` - избыточные данные (дубликаты), не использовать!

4. `players.realName` может отличаться от `vehicles.name`, если игрок сменил ник после боя

**Подробная документация:** [docs/BATTLE_RESULT_JSON_STRUCTURE.md](docs/BATTLE_RESULT_JSON_STRUCTURE.md)

### Replay Processing Flow

1. User uploads .mtreplay file(s) via `ReplayBatchUploadView`
2. `ReplayProcessingService.process_replay()`:
   - Saves file to MEDIA_ROOT via `FileStorageService`
   - Parses binary file via `Parser` (wotreplay package)
   - Extracts structured fields via `ExtractorV2`
   - Creates/updates related objects (Tank, Player, Map)
   - Creates Replay record with full JSON payload
   - Attaches all battle participants
3. Duplicate detection via unique constraint: (owner, battle_date, tank)
4. Unsupported replay versions are moved to `media/unsupported_version_replays/`

## Common Development Commands

### Setup & Run

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On macOS/Linux
# .venv\Scripts\activate   # On Windows

# Install dependencies
pip install -r requirements.txt

# Setup database
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic --noinput

# Run development server
python manage.py runserver

# Run with specific settings
DJANGO_DEBUG=True python manage.py runserver
```

### Database Operations

```bash
# Create migrations after model changes
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Open Django shell
python manage.py shell

# Reset database (SQLite only)
rm db.sqlite3
python manage.py migrate
```

### Docker Commands

```bash
# Build image
docker build -t lesta_replays .

# Run with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop containers
docker-compose down

# Rebuild and restart
docker-compose up -d --build
```

### Django Admin

```bash
# Access admin at http://localhost:8000/admin/
# Manage tanks, maps, achievements, players, and replays
```

## Environment Configuration

Required environment variables (see `.env.example`):

```bash
# Django
DJANGO_DEBUG=True              # Dev only
SECRET_KEY=...                 # Change in production

# Database (PostgreSQL)
USE_POSTGRES=1                 # Set to 1 to use PostgreSQL
POSTGRES_DB=...
POSTGRES_USER=...
POSTGRES_PASSWORD=...
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Email
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.yandex.ru
EMAIL_PORT=587
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
DEFAULT_FROM_EMAIL=...

# OAuth (django-allauth)
GOOGLE_OAUTH2_CLIENT_ID=...
GOOGLE_OAUTH2_CLIENT_SECRET=...
YANDEX_OAUTH2_CLIENT_ID=...
YANDEX_OAUTH2_CLIENT_SECRET=...

# Sentry (production monitoring)
SENTRY_DSN=...
SENTRY_ENV=production
SENTRY_TRACES_SAMPLE_RATE=0.1
SENTRY_PROFILES_SAMPLE_RATE=0.1

# Comments
SITE_ID=1
```

## Important Patterns & Conventions

### Code Style

Follow `.cursor/rules/main-django.mdc`:
- Use Django's class-based views (CBVs) for complex views
- Keep business logic in services, not views
- Use Django ORM with `select_related()` and `prefetch_related()` for performance
- Follow PEP 8 naming conventions
- Prefer descriptive names over abbreviations

### Query Optimization

```python
# Always prefetch related objects in list views
queryset = (Replay.objects
    .select_related('tank', 'owner', 'user', 'map')
    .prefetch_related('participants')
)

# Use F() expressions for atomic updates
Replay.objects.filter(pk=replay_pk).update(view_count=F('view_count') + 1)
```

### Error Handling

- Use `ReplayErrorHandler` for replay processing errors
- ParseError for unsupported replay versions (auto-archived)
- ValidationError for user-facing errors
- All exceptions logged via Python logging module
- Sentry integration captures production errors

### File Storage

- All replay files stored in `MEDIA_ROOT` (configurable via settings)
- Files named: `{original_name}` or `{stem}_{timestamp}{ext}` if duplicate
- Unsupported versions moved to `media/unsupported_version_replays/`
- File validation: max size 100MB, .mtreplay extension only

### URL Structure

```
/                          # Replay list with filters
/replays/upload/           # Batch upload modal
/replays/<pk>/             # Replay detail page
/replays/<pk>/download/    # Download .mtreplay file
/replays/filters/          # Advanced filters page
/my-replays/               # User's uploaded replays (auth required)
/accounts/login/           # Login (allauth)
/accounts/signup/          # Register (allauth)
/admin/                    # Django admin
```

### Services Architecture

When adding new functionality:
1. **Models** (`models.py`): Define data structure
2. **Services** (`services.py`): Implement business logic as standalone service classes
3. **Views** (`views.py`): Handle HTTP requests/responses, delegate to services
4. **Templates**: Display data (keep logic minimal)

Example service pattern:
```python
class MyService:
    """Service for handling X."""

    @staticmethod
    def do_something(data):
        """Process data and return result."""
        # Business logic here
        return result
```

## Known Issues & Limitations

- **No automated tests**: Critical gap - test coverage needed for parser and services
- **No linters configured**: No black, flake8, or ruff setup
- **Mixed frontend stack**: Both jQuery and vanilla JS; Tailwind CSS (CDN) + custom CSS
- **CDN dependencies**: jQuery and Tailwind loaded from CDN (consider npm/yarn)
- **Parser version support**: Older/newer replay formats may fail to parse
- **No async support**: All replay processing is synchronous (could use Celery for background processing)

## Deployment Notes

- Uses Gunicorn WSGI server (3 workers by default, configurable via GUNICORN_WORKERS)
- WhiteNoise serves static files (no need for separate static server)
- Database migrations run automatically in Docker entrypoint
- Static files collected automatically on container start
- SSL/HTTPS handled by reverse proxy (Nginx/Caddy)
- Set `DEBUG=False` in production
- Configure `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`

## Special Considerations

### Replay Parsing

- Binary format parsing in `wotreplay/` package
- Replay format can change with game updates
- Unsupported versions are archived, not deleted
- Full replay JSON stored in `Replay.payload` field for future re-processing

### Player Data

- Players auto-created/updated from replay data
- Player.name is unique (login)
- Player.real_name can change (display name)
- Clan tags updated on each replay upload
- M2M relationship tracks all battle participants

### Achievements

- Stored with local image paths (not CDN URLs)
- Split into battle/non-battle sections for display
- Mastery badges (0-4) handled separately from achievements
- Achievement data synced from Lesta API (separate process)

### Comments System

- Uses django-comments-xtd package
- Email confirmation disabled for anonymous comments
- Max thread depth: 3 levels
- Custom form: `replays.forms.SimpleCommentForm`
- Only authenticated users can comment

### Security

- CSRF protection enabled
- File upload validation (size, extension, content)
- Path traversal protection in download view
- SQL injection protection via ORM
- XSS protection via template auto-escaping
- Sentry filters out healthcheck and suspicious requests

## Performance Optimization

### Replay Detail View Optimization (2025-01)

Проведена масштабная оптимизация обработки страницы деталей реплея (`ReplayDetailView`).

**Результаты (на примере реплея с 30 игроками):**

| Метрика | До | После | Улучшение |
|---------|-----|-------|-----------|
| Время обработки | 16.30 мс | **2.70 мс** | **↓ 83%** |
| SQL запросов | 16 | **3** | **↓ 81%** |
| Парсинг JSON | 10-15 раз | **1 раз** | **↓ 90+%** |

**Ключевые изменения:**

1. **ReplayDataCache** ([replays/parser/replay_cache.py](replays/parser/replay_cache.py))
   - Кеширует данные из JSON payload
   - Ленивая загрузка свойств через `@property`
   - Парсинг JSON выполняется только один раз

2. **Batch Loading** ([replays/views.py](replays/views.py))
   - `_preload_tanks(cache)` - загрузка всех танков одним запросом
   - `_preload_achievements(cache)` - загрузка достижений одним запросом
   - Материализация QuerySet для избежания повторных `.count()`

3. **Оптимизированные методы ExtractorV2** ([replays/parser/extractor.py](replays/parser/extractor.py))
   - Все методы используют `ReplayDataCache` вместо прямого парсинга payload
   - Мемоизация справочных функций с `@lru_cache`
   - Методы принимают предзагруженные кеши (`tanks_cache`, `medals_cache`)

4. **Удаленный устаревший код:**
   - `get_player_interactions()` - вызывал N+1 запросы
   - `_avatar_info()` - делал `Tank.objects.get()` в цикле

**Инструменты для мониторинга производительности:**

```bash
# Быстрый бенчмарк
python scripts/benchmark_replay_detail.py <replay_id> [runs]

# Детальное профилирование
python scripts/profile_replay_detail.py <replay_id> [runs]

# Анализ SQL запросов
python scripts/analyze_queries.py <replay_id>
```

**Документация:** См. [docs/EXTRACTOR_OPTIMIZATION.md](docs/EXTRACTOR_OPTIMIZATION.md) для подробной информации.

**Тесты:**

```bash
# Тесты для ReplayDataCache
python manage.py test replays.tests.test_replay_cache

# Тесты для ExtractorV2
python manage.py test replays.tests.test_extractor_optimized
```

### client_adapter Integration (2025-02)

Портированы модули из клиентского кода battle_results для типизированного доступа к данным реплеев.

**Результаты:**

| Метрика | Значение |
|---------|----------|
| Модулей портировано | 8 |
| Строк кода | ~4,500 |
| Тестов | 199 (100% passed) |
| Поддержка типов боёв | 35+ (REGULAR, RANKED, EPIC, etc.) |

**Ключевые компоненты:**

1. **ReplayDataAdapter** ([replays/parser/client_adapter/adapter.py](replays/parser/client_adapter/adapter.py))
   - Извлекает battle_results из payload: `payload[1][0]`
   - Валидирует структуру данных
   - Создаёт ReusableInfo через `create_reusable_info()`
   - Кеширует результат для повторного использования

2. **ReusableInfo** ([replays/parser/client_adapter/reusable_info.py](replays/parser/client_adapter/reusable_info.py))
   - Главный контейнер данных боя
   - CommonInfo: arena_bonus_type, duration, winner_team
   - PersonalInfo: avatar (account_id, team)
   - PlayersInfo: все игроки боя (fake_name, real_name, clan)
   - VehiclesInfo: техника игроков
   - AvatarsInfo: статистика (damage, kills)

3. **ExtractorWithReusableInfo** ([replays/parser/extractor_reusable.py](replays/parser/extractor_reusable.py))
   - Расширенные методы для работы с типами боёв
   - `get_battle_type_name()` - человекочитаемое название
   - `is_random_battle()`, `is_ranked_battle()`, `is_epic_battle()`, etc.
   - `is_team_win()`, `get_team_result()` - результаты команды
   - 41 тест с полным покрытием

**Использование:**

```python
from replays.parser.client_adapter import ReplayDataAdapter
from replays.parser.extractor_reusable import ExtractorWithReusableInfo

# Создать adapter из payload
adapter = ReplayDataAdapter(replay.payload)

if not adapter.is_valid():
    logger.error(f"Invalid replay: {adapter.get_error()}")
    return

# Получить ReusableInfo
info = adapter.get_reusable_info()

# Использовать extractor для типов боёв
extractor = ExtractorWithReusableInfo(info)

print(f"Battle type: {extractor.get_battle_type_name()}")  # "Random Battle"
print(f"Win: {extractor.is_team_win()}")                    # True/False
print(f"Duration: {extractor.get_battle_duration()} sec")   # 420
```

**Константы:**

```python
from replays.parser.client_adapter import ARENA_BONUS_TYPE, PLAYER_TEAM_RESULT

# Типы боёв
ARENA_BONUS_TYPE.REGULAR = 1
ARENA_BONUS_TYPE.RANKED = 19
ARENA_BONUS_TYPE.EPIC_BATTLE = 18
# ... 35+ типов

# Результаты
PLAYER_TEAM_RESULT.WIN = 'win'
PLAYER_TEAM_RESULT.DEFEAT = 'lose'
PLAYER_TEAM_RESULT.DRAW = 'tie'
```

**Документация:** См. [docs/INTEGRATION_GUIDE.md](docs/INTEGRATION_GUIDE.md) для примеров использования.

**Тесты:**

```bash
# Все тесты client_adapter (199 тестов)
python manage.py test replays.tests.test_client_adapter

# Тесты ExtractorWithReusableInfo (41 тест)
python manage.py test replays.tests.test_extractor_reusable

# Интеграционные тесты ReplayDataAdapter (17 тестов)
python manage.py test replays.tests.test_client_adapter_integration
```
