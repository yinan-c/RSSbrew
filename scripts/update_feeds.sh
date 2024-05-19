#!/bin/bash

cd /app

/usr/local/bin/python3 manage.py update_feeds
/usr/local/bin/python3 manage.py clean_old_articles
