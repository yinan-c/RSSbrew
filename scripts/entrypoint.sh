#!/bin/bash

set -e

CRONTAB_FILE='/etc/cron.d/mycron'
echo "SHELL=/bin/bash" > $CRONTAB_FILE
echo "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" >> $CRONTAB_FILE

echo "$CRON /app/scripts/update_feeds.sh >> /var/log/cron.log 2>&1" >> $CRONTAB_FILE
echo "0 0 * * * /usr/local/bin/python3 /app/manage.py generate_digest >> /var/log/cron.log 2>&1" >> $CRONTAB_FILE

crontab $CRONTAB_FILE

printenv | grep -v "no_proxy" > /etc/environment

python3 /app/manage.py init_server

cron -f &

exec gunicorn rssbrew.wsgi:application --bind 0.0.0.0:8000
