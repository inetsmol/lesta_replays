#!/usr/bin/env bash
set -e

# Важно: БД должна быть доступна
python manage.py migrate --noinput
python manage.py compilemessages
python manage.py collectstatic --noinput

exec gunicorn lesta_replays.wsgi:application \
  --bind 0.0.0.0:8001 \
  --workers ${GUNICORN_WORKERS:-3} \
  --timeout ${GUNICORN_TIMEOUT:-60}
