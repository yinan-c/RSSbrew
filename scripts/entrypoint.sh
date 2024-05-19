#!/bin/bash

set -e

echo "$CRON /app/scripts/update_feeds.sh >> /var/log/cron.log 2>&1" | crontab -

cron

python3 manage.py init_server

exec gunicorn rssbrew.wsgi:application --bind 0.0.0.0:8000

