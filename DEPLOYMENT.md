# Руководство по развертыванию Lesta Replays

## Содержание

- [Требования](#требования)
- [Настройка окружения](#настройка-окружения)
- [База данных и миграции](#база-данных-и-миграции)
- [Статические файлы](#статические-файлы)
- [OAuth провайдеры](#oauth-провайдеры)
- [Запуск приложения](#запуск-приложения)
- [Docker развертывание](#docker-развертывание)
- [Обновление приложения](#обновление-приложения)
- [Troubleshooting](#troubleshooting)

---

## Требования

### Системные требования

- Python 3.12+
- PostgreSQL 14+ (для production) или SQLite (для development)
- Git
- Nginx (для production, опционально)

### Python зависимости

Все зависимости перечислены в `requirements.txt`

---

## Настройка окружения

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd lesta_replays
```

### 2. Создание виртуального окружения

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# или
.venv\Scripts\activate     # Windows
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Настройка переменных окружения

Скопируйте файл `.env.example` в `.env`:

```bash
cp .env.example .env
```

Отредактируйте `.env` файл и установите необходимые значения:

**Обязательные параметры:**

```bash
# Django
DJANGO_DEBUG=False                    # ВАЖНО: False для production!
SECRET_KEY=<сгенерируйте уникальный ключ>

# База данных (для PostgreSQL)
USE_POSTGRES=1
POSTGRES_DB=lesta_replays
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<надежный пароль>
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Домены
ALLOWED_HOSTS=lesta-replays.ru,www.lesta-replays.ru
CSRF_TRUSTED_ORIGINS=https://lesta-replays.ru,https://www.lesta-replays.ru

# OAuth Lesta Games
LESTA_OAUTH2_APLICATON_ID=<ваш application_id>

# OAuth Google (если используется)
GOOGLE_OAUTH2_CLIENT_ID=<ваш client_id>
GOOGLE_OAUTH2_CLIENT_SECRET=<ваш client_secret>

# OAuth Yandex (если используется)
YANDEX_OAUTH2_CLIENT_ID=<ваш client_id>
YANDEX_OAUTH2_CLIENT_SECRET=<ваш client_secret>

# Email (для уведомлений)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.yandex.ru
EMAIL_PORT=587
EMAIL_HOST_USER=<ваш email>
EMAIL_HOST_PASSWORD=<пароль>
DEFAULT_FROM_EMAIL=<от кого отправлять>

# Sentry (опционально, для мониторинга ошибок)
SENTRY_DSN=<ваш DSN>
SENTRY_ENV=production
```

**Генерация SECRET_KEY:**

```python
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## База данных и миграции

### PostgreSQL (Production)

#### 1. Установка PostgreSQL

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
```

**macOS:**
```bash
brew install postgresql@14
brew services start postgresql@14
```

#### 2. Создание базы данных

```bash
sudo -u postgres psql

# В psql консоли:
CREATE DATABASE lesta_replays;
CREATE USER lesta_user WITH PASSWORD 'надежный_пароль';
ALTER ROLE lesta_user SET client_encoding TO 'utf8';
ALTER ROLE lesta_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE lesta_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE lesta_replays TO lesta_user;
\q
```

#### 3. Применение миграций

```bash
# Создать новые миграции (после изменения models.py)
python manage.py makemigrations

# Просмотреть список миграций
python manage.py showmigrations

# Применить все миграции
python manage.py migrate

# Применить миграции конкретного приложения
python manage.py migrate replays

# Откатить миграции (ОСТОРОЖНО!)
python manage.py migrate replays 0001  # откат к миграции 0001
```

#### 4. Создание суперпользователя

```bash
python manage.py createsuperuser
```

**Важно:** Django Admin доступен по адресу `/admin/` (обратите внимание на два `n` в URL: `/adminn/`)

### SQLite (Development)

Для локальной разработки используется SQLite (файл `db.sqlite3`).

```bash
# Применить миграции
python manage.py migrate

# Сбросить базу данных (ОСТОРОЖНО!)
rm db.sqlite3
python manage.py migrate
```

---

## Статические файлы

### 1. Сборка статических файлов

```bash
# Собрать все статические файлы в STATIC_ROOT
python manage.py collectstatic --noinput

# Принудительная перезапись (если файлы изменились)
python manage.py collectstatic --clear --noinput
```

Статические файлы будут собраны в директорию `staticfiles/`.

### 2. Настройка WhiteNoise (рекомендуется)

WhiteNoise уже настроен в проекте и позволяет Django отдавать статические файлы напрямую.

**Проверка конфигурации в `settings.py`:**

```python
MIDDLEWARE = [
    # ...
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # После SecurityMiddleware!
    # ...
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
```

### 3. Настройка Nginx (опционально)

Если используете Nginx, можно отдавать статику напрямую:

```nginx
server {
    listen 80;
    server_name lesta-replays.ru;

    location /static/ {
        alias /path/to/lesta_replays/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /path/to/lesta_replays/media/;
        expires 7d;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## OAuth провайдеры

Все OAuth провайдеры настроены через `settings.py` (не требуют записей в базе данных).

### Lesta Games OpenID

1. **Зарегистрируйте приложение** на https://developers.lesta.ru/
2. **Добавьте Redirect URI:**
   - Development: `http://localhost:8000/accounts/lesta/login/callback/`
   - Production: `https://lesta-replays.ru/accounts/lesta/login/callback/`
3. **Скопируйте Application ID** в `.env`:
   ```bash
   LESTA_OAUTH2_APLICATON_ID=b351569dc0d5dc0908be75ca50534e3a
   ```

**Важно:** Lesta API требует HTTPS для production!

### Google OAuth

1. Создайте проект в [Google Cloud Console](https://console.cloud.google.com/)
2. Включите Google+ API
3. Создайте OAuth 2.0 Client ID (тип: Web application)
4. Добавьте Authorized redirect URIs:
   - `https://lesta-replays.ru/accounts/google/login/callback/`
5. Скопируйте Client ID и Client Secret в `.env`

### Yandex OAuth

1. Создайте приложение на https://oauth.yandex.ru/
2. Укажите Callback URI:
   - `https://lesta-replays.ru/accounts/yandex/login/callback/`
3. Выберите права доступа: `login:email`, `login:info`
4. Скопируйте Client ID и Client Secret в `.env`

**Проверка настройки провайдеров:**

```bash
python manage.py shell
>>> from allauth.socialaccount import app_settings
>>> app_settings.PROVIDERS
# Должны быть перечислены: lesta, google, yandex
```

---

## Запуск приложения

### Development сервер

```bash
python manage.py runserver
# Доступно по адресу: http://localhost:8000
```

### Production (Gunicorn)

#### 1. Установка Gunicorn

```bash
pip install gunicorn
```

#### 2. Запуск Gunicorn

```bash
# Базовый запуск
gunicorn lesta_replays.wsgi:application --bind 0.0.0.0:8000

# С настройками
gunicorn lesta_replays.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 3 \
  --timeout 120 \
  --access-logfile /var/log/gunicorn/access.log \
  --error-logfile /var/log/gunicorn/error.log \
  --log-level info
```

#### 3. Systemd сервис (рекомендуется)

Создайте файл `/etc/systemd/system/lesta_replays.service`:

```ini
[Unit]
Description=Lesta Replays Gunicorn
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/path/to/lesta_replays
Environment="PATH=/path/to/lesta_replays/.venv/bin"
EnvironmentFile=/path/to/lesta_replays/.env
ExecStart=/path/to/lesta_replays/.venv/bin/gunicorn \
  lesta_replays.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 3 \
  --timeout 120 \
  --access-logfile /var/log/gunicorn/access.log \
  --error-logfile /var/log/gunicorn/error.log

[Install]
WantedBy=multi-user.target
```

Запустите сервис:

```bash
sudo systemctl daemon-reload
sudo systemctl start lesta_replays
sudo systemctl enable lesta_replays  # автозапуск
sudo systemctl status lesta_replays
```

---

## Docker развертывание

### 1. Сборка образа

```bash
docker build -t lesta_replays .
```

### 2. Запуск с docker-compose

```bash
# Запуск всех сервисов (web + db)
docker-compose up -d

# Просмотр логов
docker-compose logs -f

# Остановка
docker-compose down

# Пересборка и запуск
docker-compose up -d --build
```

### 3. Выполнение команд в контейнере

```bash
# Миграции
docker-compose exec web python manage.py migrate

# Сборка статики
docker-compose exec web python manage.py collectstatic --noinput

# Создание суперпользователя
docker-compose exec web python manage.py createsuperuser

# Shell
docker-compose exec web python manage.py shell

# Bash в контейнере
docker-compose exec web bash
```

---

## Обновление приложения

### Процедура обновления (Production)

```bash
# 1. Перейти в директорию проекта
cd /path/to/lesta_replays

# 2. Активировать виртуальное окружение
source .venv/bin/activate

# 3. Получить изменения из Git
git pull origin main

# 4. Установить/обновить зависимости
pip install -r requirements.txt

# 5. Применить миграции
python manage.py migrate

# 6. Собрать статические файлы
python manage.py collectstatic --noinput

# 7. Перезапустить Gunicorn
sudo systemctl restart lesta_replays

# 8. Проверить статус
sudo systemctl status lesta_replays

# 9. Проверить логи
sudo journalctl -u lesta_replays -f
```

### Откат к предыдущей версии

```bash
# Откатить Git
git log  # найти commit hash
git checkout <commit-hash>

# Откатить миграции (если нужно)
python manage.py migrate replays 0XXX  # номер миграции

# Перезапустить
sudo systemctl restart lesta_replays
```

---

## Troubleshooting

### Проблема: "DisallowedHost at /"

**Решение:** Добавьте ваш домен в `ALLOWED_HOSTS` в `.env`:

```bash
ALLOWED_HOSTS=lesta-replays.ru,www.lesta-replays.ru,localhost
```

### Проблема: "CSRF verification failed"

**Решение:** Добавьте домены в `CSRF_TRUSTED_ORIGINS`:

```bash
CSRF_TRUSTED_ORIGINS=https://lesta-replays.ru,https://www.lesta-replays.ru
```

### Проблема: Статические файлы не загружаются

**Решение:**

1. Проверьте что выполнили `collectstatic`:
   ```bash
   python manage.py collectstatic --noinput
   ```

2. Проверьте настройки:
   ```python
   # settings.py
   STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
   STATIC_URL = '/static/'
   ```

3. Проверьте логи Nginx/Gunicorn

### Проблема: "No module named 'X'"

**Решение:**

```bash
# Убедитесь что виртуальное окружение активировано
source .venv/bin/activate

# Переустановите зависимости
pip install -r requirements.txt
```

### Проблема: Миграции не применяются

**Решение:**

```bash
# Проверьте статус миграций
python manage.py showmigrations

# Фейковое применение (если миграция уже применена вручную)
python manage.py migrate --fake replays 0001

# Пересоздать миграции (ОСТОРОЖНО!)
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
find . -path "*/migrations/*.pyc" -delete
python manage.py makemigrations
python manage.py migrate
```

### Проблема: "MultipleObjectsReturned" при OAuth авторизации

**Причина:** Дублирование записей SocialApp в базе или в settings.

**Решение:** Используйте только один способ конфигурации провайдеров:
- **Рекомендуется:** Через `settings.py` с секцией `'APP'`
- Удалите все записи из Django Admin → Social applications

### Проблема: Lesta авторизация не работает

**Проверьте:**

1. HTTPS включен (для production):
   ```python
   SECURE_SSL_REDIRECT = True
   SESSION_COOKIE_SECURE = True
   CSRF_COOKIE_SECURE = True
   ```

2. Redirect URI зарегистрирован на developers.lesta.ru:
   ```
   https://lesta-replays.ru/accounts/lesta/login/callback/
   ```

3. Application ID правильный в `.env`

4. Логи сервера:
   ```bash
   sudo journalctl -u lesta_replays -f
   ```

### Проблема: Большой размер медиа-файлов

**Решение:** Настройте периодическую очистку старых реплеев:

```bash
# Создайте cron job
crontab -e

# Добавьте задачу (например, каждую неделю)
0 3 * * 0 cd /path/to/lesta_replays && .venv/bin/python manage.py cleanup_old_replays --days=90
```

---

## Безопасность

### Чек-лист для Production

- [ ] `DEBUG = False` в `.env`
- [ ] `SECRET_KEY` сгенерирован уникальный
- [ ] `ALLOWED_HOSTS` настроен правильно
- [ ] `CSRF_TRUSTED_ORIGINS` настроен правильно
- [ ] HTTPS включен (`SECURE_SSL_REDIRECT = True`)
- [ ] PostgreSQL используется вместо SQLite
- [ ] `.env` файл не коммитится в Git (в `.gitignore`)
- [ ] Файлы логов доступны только владельцу
- [ ] Регулярные бэкапы базы данных
- [ ] Sentry настроен для мониторинга ошибок

### Резервное копирование

```bash
# Бэкап PostgreSQL
pg_dump lesta_replays > backup_$(date +%Y%m%d).sql

# Бэкап медиа-файлов
tar -czf media_backup_$(date +%Y%m%d).tar.gz media/

# Восстановление
psql lesta_replays < backup_20250118.sql
```

---

## Полезные команды

```bash
# Проверка конфигурации Django
python manage.py check

# Тестирование email
python manage.py shell
>>> from django.core.mail import send_mail
>>> send_mail('Test', 'Test message', 'from@example.com', ['to@example.com'])

# Очистка сессий
python manage.py clearsessions

# Проверка производительности
python manage.py runserver --nothreading --noreload

# SQL запросы миграций (не применяя)
python manage.py sqlmigrate replays 0001
```

---

## Поддержка

При возникновении проблем:

1. Проверьте логи приложения
2. Проверьте логи веб-сервера (Nginx/Gunicorn)
3. Проверьте Sentry (если настроен)
4. Обратитесь к документации Django: https://docs.djangoproject.com/

---

**Дата последнего обновления:** 2025-01-18
