from django.core.management.base import BaseCommand
from FeedManager.models import ProcessedFeed, OriginalFeed, Article
import feedparser
from datetime import datetime
import pytz
import re
import os
from openai import OpenAI
from django.conf import settings
from FeedManager.utils import passes_filters, match_content, generate_untitled, clean_html, clean_url
import logging
import tiktoken
from django.db import transaction

logger = logging.getLogger('feed_logger')

OPENAI_PROXY = os.environ.get('OPENAI_PROXY')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL') or 'https://api.openai.com/v1'

class Command(BaseCommand):
    help = 'Updates and processes RSS feeds based on defined schedules and filters.'

    def add_arguments(self, parser):
        parser.add_argument('-f', '--feed', type=int, help='ID of the ProcessedFeed to update')

    def handle(self, *args, **options):
        feed_id = options.get('feed')
        if feed_id:
            try:
                feed = ProcessedFeed.objects.get(id=feed_id)
                self.stdout.write(f'Processing single feed: {feed.name}')
                self.update_feed(feed)
            except ProcessedFeed.DoesNotExist:
                raise CommandError('ProcessedFeed "%s" does not exist' % feed_id)
        else:
            processed_feeds = ProcessedFeed.objects.all()
            for feed in processed_feeds:
                self.stdout.write(f'Processing feed: {feed.name}')
                self.update_feed(feed)

    def update_feed(self, feed):
        self.current_n_processed = 0
        entries = []
        for original_feed in feed.feeds.all():
            try:
                parsed_feed = feedparser.parse(original_feed.url)
                # first sort by published date, then only process the most recent max_articles_to_keep articles 
                if parsed_feed.entries: 
                    parsed_feed.entries.sort(key=lambda x: x.get('published_parsed', []), reverse=True)
#                    self.stdout.write(f'  Found {len(parsed_feed.entries)} entries in feed {original_feed.url}')
                    entries.extend((entry, original_feed) for entry in parsed_feed.entries[:original_feed.max_articles_to_keep])
            except Exception as e:
                logger.error(f'Failed to parse feed {original_feed.url}: {str(e)}')
                continue
        entries.sort(key=lambda x: x[0].get('published_parsed', []), reverse=True)
        for entry, original_feed in entries:
            try:
                self.process_entry(entry, feed, original_feed)
            except Exception as e:
                logger.error(f'Failed to process entry: {str(e)}')

    def process_entry(self, entry, feed, original_feed):
        # 先检查 filter 再检查数据库
        if passes_filters(entry, feed, 'feed_filter'):
            existing_article = Article.objects.filter(url=clean_url(entry.link)).first()
            if not existing_article:
                # 如果不存在，则创建新文章
                article = Article(
                    original_feed=original_feed,
                    title=entry.title,
                    url= clean_url(entry.link),
                    published_date=datetime(*entry.published_parsed[:6], tzinfo=pytz.UTC) if 'published_parsed' in entry else datetime.now(pytz.UTC),
                    content=entry.content[0].value if 'content' in entry else entry.description
                )
                logger.info(f'  Added new article: {article.title}')
                if self.current_n_processed < feed.max_articles_to_process_per_interval and passes_filters(entry, feed, 'summary_filter'):
                    self.generate_summary(article, feed.model, feed.summary_language)
                    logger.info(f'  Summary generated for article: {article.title}')
                    self.current_n_processed += 1
                article.save()

    def clean_txt_and_truncate(self, article, model):
        cleaned_article = clean_html(article.content)

        encoding = tiktoken.encoding_for_model(model)
        token_length = len(encoding.encode(cleaned_article))

        max_length_of_models = {
            'gpt-3.5-turbo': 16385,
            'gpt-4': 128000,
            'gpt-4-32k': 128000
        }

        # Truncate the text if it exceeds the model's token limit
        if token_length > max_length_of_models[model]:
            truncated_article = encoding.decode(encoding.encode(cleaned_article)[:max_length_of_models[model]])
            return truncated_article
        else:
            return cleaned_article

    def generate_summary(self, article, model, language):
        if not model or not OPENAI_API_KEY:
            return   
        try:
            client_params = {
                "api_key": OPENAI_API_KEY,
                "base_url": OPENAI_BASE_URL
            }
            if OPENAI_PROXY:
                client_params["http_client"] = httpx.Client(proxy=OPENAI_PROXY)
    
            client = OpenAI(**client_params)
            truncated_query = self.clean_txt_and_truncate(article, model)
            messages = [
                {"role": "user", "content": f"{truncated_query}"},
                {"role": "assistant", "content": f"Please summarize this article, first extract 5 keywords, output in the same line, then line break, write a summary containing all the points in 150 words in {language}, output in order by points, and output in the following format '<br><br>Summary:', <br> is the line break of HTML, 2 must be retained when output, and must be before the word 'Summary:', finally, output result in {language}."}
            ]
    
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
            )
            article.summary = completion.choices[0].message.content
            article.summarized = True
            article.save()
        except Exception as e:
            logger.error(f'Failed to generate summary for article {article.title}: {str(e)}')