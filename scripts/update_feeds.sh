#!/bin/bash

cd /app

python manage.py update_feeds
python manage.py clean_old_articles
