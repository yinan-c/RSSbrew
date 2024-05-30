from huey.contrib.djhuey import periodic_task
from huey import crontab
from django.core.management import call_command
from django.conf import settings
import os
import logging
from FeedManager.utils import parse_cron
logger = logging.getLogger('feed_logger')

CRON = os.getenv('CRON', '0 * * * *')  # default to every hour
cron_settings = parse_cron(CRON)
logger.info(f"Scheduled task with CRON settings: {cron_settings}")

@periodic_task(crontab(
    minute=cron_settings['minute'],
    hour=cron_settings['hour'],
    day=cron_settings['day'],
    month=cron_settings['month'],
    day_of_week=cron_settings['day_of_week']),
    retries=3,)
def update_feeds_task():
    call_command('update_feeds')
    call_command('clean_old_articles')


CRON_DIGEST = os.getenv('CRON_DIGEST', '0 0 * * *') # default to every day
cron_settings = parse_cron(CRON_DIGEST)
logger.info(f"Scheduled task with CRON settings: {cron_settings}")

@periodic_task(crontab(
    minute=cron_settings['minute'],
    hour=cron_settings['hour'],
    day=cron_settings['day'],
    month=cron_settings['month'],
    day_of_week=cron_settings['day_of_week']),
    retries=3,)
def generate_digest_task():
    call_command('generate_digest')