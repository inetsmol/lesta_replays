#!/usr/bin/env bash
set -e

# Важно: БД должна быть доступна
python manage.py migrate --noinput
python manage.py collectstatic --noinput

# Health endpoint можешь сделать в Django (например, path("health/", ...))
exec gunicorn lesta_replays.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers ${GUNICORN_WORKERS:-3} \
  --timeout ${GUNICORN_TIMEOUT:-60}
