from huey.contrib.djhuey import periodic_task, task
from huey import crontab
from django.core.management import call_command
from django.conf import settings
import os
import logging
from FeedManager.utils import parse_cron
logger = logging.getLogger('feed_logger')

CRON = os.getenv('CRON', '0 * * * *')  # default to every hour
cron_settings = parse_cron(CRON)
logger.debug(f"Scheduled task with CRON settings: {cron_settings}")

@periodic_task(crontab(
    minute=cron_settings['minute'],
    hour=cron_settings['hour'],
    day=cron_settings['day'],
    month=cron_settings['month'],
    day_of_week=cron_settings['day_of_week']),
    retries=3,)
def update_feeds_task():
    try:
        call_command('update_feeds')
    except Exception as e:
        logger.error(f"Error in update_feeds_task: {str(e)}")
        raise
    
    try:
        call_command('clean_old_articles')
    except Exception as e:
        logger.error(f"Error in clean_old_articles: {str(e)}")
        raise

# TODO Maybe add time of the day to generate digest after digest_frequency
CRON_DIGEST = os.getenv('CRON_DIGEST', '0 0 * * *') # default to every day
cron_settings = parse_cron(CRON_DIGEST)
logger.debug(f"Scheduled task with CRON settings: {cron_settings}")

@periodic_task(crontab(
    minute=cron_settings['minute'],
    hour=cron_settings['hour'],
    day=cron_settings['day'],
    month=cron_settings['month'],
    day_of_week=cron_settings['day_of_week']),
    retries=3,)
def generate_digest_task():
    call_command('generate_digest')

@task(retries=3)
def async_update_feeds_and_digest(feed_name):
    call_command('update_feeds', name=feed_name)
    call_command('generate_digest', name=feed_name)

@task(retries=3)
def clean_old_articles(feed_id):
    call_command('clean_old_articles', feed=feed_id)