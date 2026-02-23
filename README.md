# Lesta Replays

Веб-приложение на Django для загрузки, парсинга и публикации реплеев **«Мир танков»** (`.mtreplay`) с фильтрацией, статистикой боя и пользовательскими профилями.

## Что делает проект

- Загружает один или несколько реплеев и извлекает данные боя.
- Показывает список реплеев с фильтрами, сортировкой и пагинацией.
- Отображает детальную статистику боя: урон, фраги, ассист, блок, достижения, карту, режим и т.д.
- Поддерживает авторизацию (включая social login), комментарии и голосование.
- Ведет профили пользователей, статистику и базовые функции подписки.
- Отдает health endpoint: `GET /health/`.

## Стек

- Python 3.12, Django 5.2
- Gunicorn + WhiteNoise
- PostgreSQL (production) / SQLite (dev)
- Tailwind CSS (сборка внутри Docker-образа)
- Docker / Docker Compose

## Быстрый старт в Docker

Проект уже содержит `docker-compose.yml` с сервисом `lesta-app` и готовым образом `biggarik/lesta_replays:latest`.

Требования: установленный Docker и Docker Compose plugin.

### 1. Подготовка

```bash
git clone <repo-url>
cd lesta_replays
cp .env.example .env
```

Отредактируйте `.env` минимум под ваш сценарий:

- `DJANGO_DEBUG=True` для локального запуска без reverse proxy.
- `USE_POSTGRES=1` и `POSTGRES_*`, если используете PostgreSQL.
- OAuth и email-переменные только если эти функции нужны.

### 2. Запуск

```bash
docker compose pull
docker compose up -d
```

Приложение будет доступно на `http://localhost:8001`.

### 3. Проверка

```bash
docker compose ps
docker compose logs -f lesta-app
curl http://localhost:8001/health/
```

После первого запуска при необходимости создайте администратора:

```bash
docker compose exec lesta-app python manage.py createsuperuser
```

## Развертывание в Docker (production)

1. Используйте внешний PostgreSQL (`USE_POSTGRES=1`) и не храните production-данные в SQLite внутри контейнера.
2. Держите volume для медиа (`./media:/app/media`) - он уже прописан в `docker-compose.yml`.
3. Ставьте reverse proxy (Nginx/Traefik/Caddy) перед приложением и TLS.
4. Для production выставляйте `DJANGO_DEBUG=False`.
5. Проверьте доступность домена в `ALLOWED_HOSTS` и `CSRF_TRUSTED_ORIGINS` в `lesta_replays/settings.py`.

Важно: при старте контейнера entrypoint автоматически выполняет:

- `python manage.py migrate`
- `python manage.py compilemessages`
- `python manage.py collectstatic --noinput`

## Обновление приложения в Docker

### Вариант A: если используете образ из реестра

```bash
git pull
docker compose pull
docker compose up -d
docker compose logs -f --tail=200 lesta-app
```

Что происходит:

- подтягивается новая версия образа;
- контейнер перезапускается;
- миграции/статика применяются автоматически через entrypoint.

### Вариант B: если собираете образ локально

```bash
git pull
docker build -t lesta-replays:local .
docker run -d \
  --name lesta-replays-app \
  --restart unless-stopped \
  --env-file .env \
  -p 8001:8001 \
  -v "$(pwd)/media:/app/media" \
  lesta-replays:local
```

## Резервные копии и откат

```bash
# backup медиа
tar -czf media_backup_$(date +%F).tar.gz media/
```

Для PostgreSQL добавьте регулярный `pg_dump` на стороне БД.

Перед обновлением рекомендуемый минимум:

1. Сделать backup медиа.
2. Сделать backup БД.
3. Зафиксировать текущий тег образа.

Для отката верните предыдущий тег в `docker-compose.yml` и выполните:

```bash
docker compose pull
docker compose up -d
```

## Сборка Tailwind после изменений

Если вы меняли шаблоны или `static/css/input.css`, пересоберите CSS:

```bash
# один раз собрать (minified)
npm run build:css

# режим разработки: автопересборка при изменениях
npm run watch:css
```

Если запускаете проект локально без Docker и хотите обновить Django staticfiles:

```bash
python manage.py collectstatic --noinput
```

Если работаете через Docker, Tailwind собирается на этапе сборки образа,
поэтому после изменений достаточно пересобрать контейнер:

```bash
docker compose up -d --build
```

## Полезные команды

```bash
# суперпользователь
docker compose exec lesta-app python manage.py createsuperuser

# shell Django
docker compose exec lesta-app python manage.py shell

# список миграций
docker compose exec lesta-app python manage.py showmigrations

# ручной health-check
curl http://localhost:8001/health/
```

## Важные нюансы

- Админка доступна по пути `/adminn/` (не `/admin/`).
- Если `USE_POSTGRES=0`, используется SQLite (`db.sqlite3`) внутри контейнера.
- При `DJANGO_DEBUG=False` включается `SECURE_SSL_REDIRECT`; для корректной работы нужен reverse proxy с HTTPS.
- Рекомендуется использовать фиксированный тег образа вместо `latest` для предсказуемых обновлений.

## Структура репозитория

- `lesta_replays/` - настройки Django и корневые URL.
- `replays/` - основная бизнес-логика (реплеи, профиль, API, сервисы, парсер).
- `news/` - модуль новостей.
- `docker/entrypoint.sh` - стартовые команды контейнера.
- `docker-compose.yml` - быстрый Docker запуск.
- `DEPLOYMENT.md` - расширенная документация по деплою и эксплуатации.
