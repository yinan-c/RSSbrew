import json
import logging
import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

import feedparser
import pytz
import requests
from fake_useragent import UserAgent

from FeedManager.models import Article, ProcessedFeed
from FeedManager.utils import clean_url, generate_summary, generate_untitled, passes_filters

logger = logging.getLogger("feed_logger")

# A 429 asking us to wait at most this many seconds is retried once in-place;
# longer waits are deferred to the next scheduled run instead of blocking it.
RATE_LIMIT_MAX_INLINE_WAIT = 15
# Assumed wait when a 429 comes without a usable Retry-After/reset header.
RATE_LIMIT_DEFAULT_RETRY_AFTER = 60


def parse_retry_after(response):
    """Seconds to wait after a 429, from Retry-After (seconds or HTTP-date)
    or the reddit-style X-Ratelimit-Reset header."""
    for header in ("Retry-After", "X-Ratelimit-Reset"):
        value = response.headers.get(header)
        if not value:
            continue
        try:
            return max(int(float(value)), 0)
        except ValueError:
            pass
        try:
            retry_at = parsedate_to_datetime(value)
            return max(int((retry_at - timezone.now()).total_seconds()), 0)
        except (TypeError, ValueError):
            continue
    return RATE_LIMIT_DEFAULT_RETRY_AFTER


def parse_date_fallback(entry):
    """
    Fallback date parser for entries where feedparser couldn't parse the date.
    Tries to parse common date formats that might be missing timezone info.
    """
    # First check if published_parsed exists and is valid
    published_parsed = entry.get("published_parsed")
    if published_parsed is not None:
        return datetime(*published_parsed[:6]).replace(tzinfo=pytz.UTC)

    # Try to parse from the raw published date string
    published = entry.get("published")
    if published:
        date_str = published.strip()

        # Common date formats that might be missing timezone
        date_formats = [
            # RFC 822 style without timezone
            "%a, %d %b %Y %H:%M:%S",
            "%a, %d %b %y %H:%M:%S",
            "%d %b %Y %H:%M:%S",
            "%d %b %y %H:%M:%S",
            # ISO-like formats
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            # Just date, no time
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d %b %Y",
            "%d %b %y",
        ]

        for fmt in date_formats:
            try:
                # Parse the date and assume UTC if no timezone specified
                parsed_date = datetime.strptime(date_str, fmt)
                return parsed_date.replace(tzinfo=pytz.UTC)
            except ValueError:
                continue

        # If the string ends with a timezone abbreviation we don't recognize,
        # try removing it and parsing again
        if len(date_str) > 3:
            # Try removing last word (potential timezone)
            parts = date_str.rsplit(None, 1)
            if len(parts) == 2:
                date_str_no_tz = parts[0]
                for fmt in date_formats:
                    try:
                        parsed_date = datetime.strptime(date_str_no_tz, fmt)
                        return parsed_date.replace(tzinfo=pytz.UTC)
                    except ValueError:
                        continue

    # If all parsing attempts fail, return current time
    return timezone.now()


def fetch_feed(url: str, last_modified: datetime, user_agent: str | None = None):
    """Fetch a feed URL.

    A `user_agent` is sent as-is; when it is None a random browser User-Agent is used,
    which is the historical behaviour.
    """
    headers = {}
    # Try comment out the following line to see if it works
    if last_modified:
        headers["If-Modified-Since"] = last_modified.strftime("%a, %d %b %Y %H:%M:%S GMT")
    headers["User-Agent"] = user_agent.strip() if user_agent else UserAgent().random.strip()
    try:
        for attempt in range(2):
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                feed = feedparser.parse(response.text)
                return {"feed": feed, "status": "updated", "last_modified": response.headers.get("Last-Modified")}
            elif response.status_code == 304:
                # ! Why is it taking so long to show not_modified? 8 seconds
                # Maybe it's because of the User-Agent or the If-Modified-Since header?
                return {"feed": None, "status": "not_modified", "last_modified": response.headers.get("Last-Modified")}
            elif response.status_code == 429:
                retry_after = parse_retry_after(response)
                if attempt == 0 and retry_after <= RATE_LIMIT_MAX_INLINE_WAIT:
                    logger.info(f"Rate limited on {url}, retrying in {retry_after}s")
                    time.sleep(max(retry_after, 1))
                    continue
                logger.warning(f"Rate limited on {url}, deferring to the next run (retry after {retry_after}s)")
                return {"feed": None, "status": "rate_limited", "retry_after": retry_after}
            else:
                logger.error(f"Failed to fetch feed {url}: {response.status_code}")
                return {"feed": None, "status": "failed"}

    except Exception as e:
        logger.error(f"Failed to fetch feed {url}: {e!s}")
        return {"feed": None, "status": "failed"}


class Command(BaseCommand):
    help = "Updates and processes RSS feeds based on defined schedules and filters."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Rate limits (e.g. reddit's) are per client, not per feed, so once a host
        # returns 429 every other feed on it is skipped for the rest of this run.
        self.host_backoff_until = {}

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
        entries: list[dict] = []
        current_modified = feed.last_modified
        min_new_modified = None
        logger.debug(f"  Current last modified: {current_modified} for feed {feed.name}")
        for original_feed in feed.get_all_feeds():
            host = urlparse(original_feed.url).netloc.lower()
            if self.host_backoff_until.get(host, 0) > time.monotonic():
                # Not a feed failure, so leave `valid` untouched; the next run retries.
                logger.warning(f"  Skipping {original_feed.url}: {host} is rate limited")
                continue
            feed_data = fetch_feed(
                original_feed.url, current_modified, user_agent=original_feed.get_effective_user_agent()
            )
            # update feed.last_modified based on earliest last_modified of all original_feeds
            if feed_data["status"] == "updated":
                original_feed.valid = True
                original_feed.save()
                logger.debug(
                    f"  Feed {original_feed.url} updated, the new modified time is {feed_data['last_modified']}"
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
                    parsed_feed.entries.sort(key=lambda x: x.get("published_parsed") or [], reverse=True)
                    #                    self.stdout.write(f'  Found {len(parsed_feed.entries)} entries in feed {original_feed.url}')
                    entries.extend(
                        {"entry": entry, "original_feed": original_feed}
                        for entry in parsed_feed.entries[: original_feed.max_articles_to_keep]
                    )
            elif feed_data["status"] == "not_modified":
                original_feed.valid = True
                original_feed.save()
                logger.debug(f"  Feed {original_feed.url} not modified")
                logger.debug(
                    f"  Feed {original_feed.url} modified time is {feed_data['last_modified']} and the current feed modified time is {current_modified}"
                )
                continue
            elif feed_data["status"] == "rate_limited":
                retry_after = feed_data.get("retry_after") or RATE_LIMIT_DEFAULT_RETRY_AFTER
                self.host_backoff_until[host] = time.monotonic() + retry_after
                # Not a feed failure, so leave `valid` untouched; the next run retries.
                continue
            elif feed_data["status"] == "failed":
                logger.error(f" Failed to fetch feed {original_feed.url}")
                original_feed.valid = False
                original_feed.save()
                continue
        if min_new_modified:
            feed.last_modified = min_new_modified
            feed.save()
        entries.sort(key=lambda x: x["entry"].get("published_parsed") or timezone.now().timetuple(), reverse=True)
        for item in entries:
            try:
                self.process_entry(item["entry"], feed, item["original_feed"])
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
                    published_date=parse_date_fallback(entry),
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
                    prompt = f"Please summarize this article, and output the result only in JSON format. First item of the json is a one-line summary in 15 words or 30 characters (depending on the output language is word-based or character-based) named as 'summary_one_line', second item is the 150-words/characters summary named as 'summary_long'. Output result in {feed.summary_language} language."
                    output_mode = "json"
                    effective_model = feed.get_effective_summary_model()
                    if feed.translate_title:
                        translate_prompt = f"Please translate the article title to {feed.summary_language} language, and output plain text only."
                        article.title = generate_summary(
                            article,
                            effective_model,
                            output_mode="translate",
                            prompt=translate_prompt,
                        )
                    if feed.additional_prompt:
                        prompt = feed.additional_prompt
                        output_mode = "HTML"

                    summary_results = generate_summary(article, effective_model, output_mode, prompt)
                    # TODO the JSON mode parse is hard-coded as is the default prompt, maybe support automatic json parsing in the future
                    if summary_results:
                        try:
                            if output_mode == "json":
                                json_result = json.loads(summary_results)
                                article.summary = json_result["summary_long"]
                                article.summary_one_line = json_result["summary_one_line"]
                                article.summarized = True
                                article.custom_prompt = False
                                logger.info(f"  Summary generated for article: {article.title} (JSON mode)")
                            else:
                                # HTML or custom prompt response
                                article.summary = summary_results
                                article.summarized = True
                                article.custom_prompt = True
                                logger.info(f"  Summary generated for article: {article.title} (custom prompt)")
                            article.save()
                        except (json.JSONDecodeError, KeyError) as e:
                            logger.warning(f"  Failed to parse summary JSON for {article.title}: {e!s}")
                            article.summary = str(summary_results) if summary_results else ""
                            article.summarized = True
                            article.custom_prompt = True
                            article.save()
                        self.current_n_processed += 1
                    else:
                        logger.warning(f"  No summary generated for article: {article.title}")
