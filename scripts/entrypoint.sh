#!/bin/bash

set -e

#CRONTAB_FILE='/etc/cron.d/mycron'
#echo "SHELL=/bin/bash" > $CRONTAB_FILE
#echo "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" >> $CRONTAB_FILE

#echo "$CRON /app/scripts/update_feeds.sh >> /var/log/cron.log 2>&1" >> $CRONTAB_FILE
#echo "0 0 * * * /usr/local/bin/python3 /app/manage.py generate_digest >> /var/log/cron.log 2>&1" >> $CRONTAB_FILE

#crontab $CRONTAB_FILE

#printenv | grep -v "no_proxy" > /etc/environment

python3 /app/manage.py init_server

#cron -f &

mkdir -p /app/logs
python3 /app/manage.py run_huey >> /app/logs/huey.log 2>&1 &

APP_PORT=${INTERNAL_PORT:-8000}

# Configure Gunicorn to better handle slow/idle client uploads
# Defaults can be overridden via env vars in docker-compose
WORKERS=${WEB_CONCURRENCY:-2}
THREADS=${THREADS:-4}
TIMEOUT=${GUNICORN_TIMEOUT:-120}
GRACEFUL_TIMEOUT=${GUNICORN_GRACEFUL_TIMEOUT:-120}
KEEP_ALIVE=${GUNICORN_KEEP_ALIVE:-2}
ACCESS_LOG=${GUNICORN_ACCESS_LOG:--}
WORKER_CLASS=${GUNICORN_WORKER_CLASS:-gthread}

exec gunicorn rssbrew.wsgi:application \
  --bind 0.0.0.0:${APP_PORT} \
  --workers ${WORKERS} \
  --worker-class ${WORKER_CLASS} \
  --threads ${THREADS} \
  --timeout ${TIMEOUT} \
  --graceful-timeout ${GRACEFUL_TIMEOUT} \
  --keep-alive ${KEEP_ALIVE} \
  --access-logfile ${ACCESS_LOG}
