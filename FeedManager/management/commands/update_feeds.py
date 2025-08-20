import json
import logging
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

import feedparser
import pytz
import requests
from fake_useragent import UserAgent

from FeedManager.models import Article, ProcessedFeed
from FeedManager.utils import clean_url, generate_summary, generate_untitled, passes_filters

logger = logging.getLogger("feed_logger")


def fetch_feed(url: str, last_modified: datetime):
    headers = {}
    ua = UserAgent()
    # Try comment out the following line to see if it works
    if last_modified:
        headers["If-Modified-Since"] = last_modified.strftime("%a, %d %b %Y %H:%M:%S GMT")
    headers["User-Agent"] = ua.random.strip()
    try:
        #        print(time.time())
        response = requests.get(url, headers=headers, timeout=30)
        #        print(time.time())
        if response.status_code == 200:
            feed = feedparser.parse(response.text)
            return {"feed": feed, "status": "updated", "last_modified": response.headers.get("Last-Modified")}
        elif response.status_code == 304:
            # ! Why is it taking so long to show not_modified? 8 seconds
            # Maybe it's because of the User-Agent or the If-Modified-Since header?
            # print(time.time())
            return {"feed": None, "status": "not_modified", "last_modified": response.headers.get("Last-Modified")}
        else:
            logger.error(f"Failed to fetch feed {url}: {response.status_code}")
            return {"feed": None, "status": "failed"}

    except Exception as e:
        logger.error(f"Failed to fetch feed {url}: {e!s}")
        return {"feed": None, "status": "failed"}


class Command(BaseCommand):
    help = "Updates and processes RSS feeds based on defined schedules and filters."

    def add_arguments(self, parser):
        parser.add_argument("-n", "--name", type=str, help="Name of the ProcessedFeed to update")

    def handle(self, *args, **options):
        feed_name = options.get("name")
        if feed_name:
            try:
                feed = ProcessedFeed.objects.get(name=feed_name)
                logger.info(f"Processing single feed: {feed.name} at {timezone.now()}")
                self.update_feed(feed)
            except ProcessedFeed.DoesNotExist:
                raise CommandError(f'ProcessedFeed "{feed_name}" does not exist') from None
            except Exception as e:
                logger.error(f"Error processing feed {feed_name}: {e!s}")
        else:
            processed_feeds = ProcessedFeed.objects.all()
            for feed in processed_feeds:
                try:
                    logger.info(f"Processing feed: {feed.name} at {timezone.now()}")
                    self.update_feed(feed)
                except Exception as e:
                    logger.error(f"Error processing feed {feed.name}: {e!s}")
                    continue  # make sure to continue to the next feed

    def update_feed(self, feed):
        self.current_n_processed = 0
        entries = []
        current_modified = feed.last_modified
        min_new_modified = None
        logger.debug(f"  Current last modified: {current_modified} for feed {feed.name}")
        for original_feed in feed.feeds.all():
            feed_data = fetch_feed(original_feed.url, current_modified)
            # update feed.last_modified based on earliest last_modified of all original_feeds
            if feed_data["status"] == "updated":
                original_feed.valid = True
                original_feed.save()
                logger.debug(
                    f'  Feed {original_feed.url} updated, the new modified time is {feed_data["last_modified"]}'
                )
                new_modified = (
                    datetime.strptime(feed_data["last_modified"], "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=pytz.UTC)
                    if feed_data["last_modified"]
                    else None
                )
                if new_modified and (not min_new_modified or new_modified < min_new_modified):
                    min_new_modified = new_modified

                parsed_feed = feed_data["feed"]
                # first sort by published date, then only process the most recent max_articles_to_keep articles
                if parsed_feed.entries:
                    parsed_feed.entries.sort(key=lambda x: x.get("published_parsed", []), reverse=True)
                    #                    self.stdout.write(f'  Found {len(parsed_feed.entries)} entries in feed {original_feed.url}')
                    entries.extend(
                        (entry, original_feed) for entry in parsed_feed.entries[: original_feed.max_articles_to_keep]
                    )
            elif feed_data["status"] == "not_modified":
                original_feed.valid = True
                original_feed.save()
                logger.debug(f"  Feed {original_feed.url} not modified")
                logger.debug(
                    f'  Feed {original_feed.url} modified time is {feed_data["last_modified"]} and the current feed modified time is {current_modified}'
                )
                continue
            elif feed_data["status"] == "failed":
                logger.error(f" Failed to fetch feed {original_feed.url}")
                original_feed.valid = False
                original_feed.save()
                continue
        if min_new_modified:
            feed.last_modified = min_new_modified
            feed.save()
        entries.sort(key=lambda x: x[0].get("published_parsed", timezone.now().timetuple()), reverse=True)
        for entry, original_feed in entries:
            try:
                self.process_entry(entry, feed, original_feed)
            except Exception as e:
                logger.error(f"Failed to process entry: {e!s}")

    def process_entry(self, entry, feed, original_feed):
        # 先检查 filter 再检查数据库
        if passes_filters(entry, feed, "feed_filter"):
            existing_article = Article.objects.filter(link=clean_url(entry.link), original_feed=original_feed).first()
            logger.debug(
                f"  Already in db: {entry.title}" if existing_article else f"  Processing new article: {entry.title}"
            )
            if not existing_article:
                # If not exists, create new article
                article = Article(
                    original_feed=original_feed,
                    title=generate_untitled(entry),
                    link=clean_url(entry.link),
                    published_date=datetime(*entry.published_parsed[:6], tzinfo=pytz.UTC)
                    if "published_parsed" in entry
                    else timezone.now(),
                    content=(
                        entry.content[0].value
                        if "content" in entry
                        else (entry.description if "description" in entry else "")
                    ),
                )
                article.save()
                # Note: if article already exists in database (not new), no need to waste tokens for summary
                #            else:
                #                article = existing_article
                if self.current_n_processed < feed.articles_to_summarize_per_interval and passes_filters(
                    entry, feed, "summary_filter"
                ):  # and not article.summarized:
                    prompt = f"Please summarize this article, and output the result only in JSON format. First item of the json is a one-line summary in 15 words named as 'summary_one_line', second item is the 150-word summary named as 'summary_long'. Output result in {feed.summary_language} language."
                    output_mode = "json"
                    if feed.translate_title:
                        translate_prompt = f"Please translate the article title to {feed.summary_language} language, and output plain text only."
                        article.title = generate_summary(
                            article,
                            feed.model,
                            output_mode="translate",
                            prompt=translate_prompt,
                            other_model=feed.other_model,
                        )
                    if feed.additional_prompt:
                        prompt = feed.additional_prompt
                        output_mode = "HTML"

                    summary_results = generate_summary(article, feed.model, output_mode, prompt, feed.other_model)
                    # TODO the JSON mode parse is hard-coded as is the default prompt, maybe support automatic json parsing in the future
                    try:
                        json_result = json.loads(summary_results)
                        article.summary = json_result["summary_long"]
                        article.summary_one_line = json_result["summary_one_line"]
                        article.summarized = True
                        article.custom_prompt = False
                        logger.info(f"  Summary generated for article: {article.title}")
                        article.save()
                    except Exception:
                        article.summary = summary_results
                        article.summarized = True
                        article.custom_prompt = True
                        logger.info(f"  Summary generated for article: {article.title}")
                        article.save()
                    self.current_n_processed += 1
