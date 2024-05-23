from django.core.management.base import BaseCommand
from FeedManager.models import ProcessedFeed, OriginalFeed, Article
import feedparser
import requests
import xml.etree.ElementTree as ET
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
from email.utils import parsedate_tz
import time

logger = logging.getLogger('feed_logger')

OPENAI_PROXY = os.environ.get('OPENAI_PROXY')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL') or 'https://api.openai.com/v1'

class Entry:
    ''' This class is used to convert a dictionary parsed by xml.etree.ElementTree to an object that can be processed by process_entry '''
    def __init__(self, entry_dict):
        self.title = entry_dict.get('title')
        self.link = entry_dict.get('link')
        self.id = entry_dict.get('id', self.link)
        self.author = entry_dict.get('author', 'Unknown')
        self.published = entry_dict.get('published')
        self.published_parsed = self.parse_published_date(entry_dict.get('published'))
        self.content = [{'type': 'text/html', 'value': entry_dict.get('content', '')}]
        self.description = entry_dict.get('description', '')

    def parse_published_date(self, date_str):
        # Convert string date to struct_time, expecting the date_str to be in a standard format
        time_tuple = parsedate_tz(date_str)
        if time_tuple:
            return datetime(*time_tuple[:6], tzinfo=pytz.UTC).timetuple()
        return datetime.now(pytz.UTC).timetuple()

    def get(self, attr, default=None):
        return getattr(self, attr, default)

def parse_xml_entry(item):
    '''
    #! This part is for xml feeds cannot be parsed by feedparser
    #! The goal is to convert the xml feed to a list of Entry objects that can be processed by process_entry
    #! I don't have much examples of this, so hard-coded for now based on https://hostloc.com/forum.php?mod=rss&fid=45&auth=0
    '''
    entry_dict = {
        'title': item.find('title').text,
        'link': item.find('link').text,
        'id': item.find('guid').text if item.find('guid') is not None else item.find('link').text,
        'published': item.find('pubDate').text,
        'author': item.find('author').text if item.find('author') is not None else "Unknown",
        'content': item.find('description').text,
        'description': item.find('description').text,
    }
    return Entry(entry_dict)

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
                else:
                    # Fallback to requests and ElementTree
                    response = requests.get(original_feed.url)
                    if response.status_code == 200:
                        root = ET.fromstring(response.content)
                        for item in root.findall('.//item'):
                            # Manually create an entry dict and then convert to an Entry object
                            entry_object = parse_xml_entry(item)
                            entries.append((entry_object, original_feed))
                    else:
                        raise Exception(f"HTTP error {response.status_code} while fetching {original_feed.url}")
            except Exception as e:
                logger.error(f'Failed to parse feed {original_feed.url}: {str(e)}')
                continue
            
        # Sort all fetched and fallback entries by published date
        entries.sort(key=lambda x: x[0].get('published_parsed', []), reverse=True)
        for entry, original_feed in entries:
#            logger.debug(f"Processing entry: {entry.title}, Feed: {original_feed}")
            try:
                self.process_entry(entry, feed, original_feed)
            except Exception as e:
                logger.error(f'Failed to process entry {entry.title}: {str(e)}')

    def process_entry(self, entry, feed, original_feed):
        # 先检查 filter 再检查数据库
        if passes_filters(entry, feed, 'feed_filter'):
            existing_article = Article.objects.filter(url=clean_url(entry.link), original_feed=original_feed).first()
            if not existing_article:
                # 如果不存在，则创建新文章
                article = Article(
                    original_feed=original_feed,
                    title=entry.title,
                    url= clean_url(entry.link),
                    published_date=datetime(*entry.published_parsed[:6], tzinfo=pytz.UTC) if entry.published_parsed else datetime.now(pytz.UTC),
                    # ! This fixes the bug showing "Failed to process entry: argument of type 'Entry' is not iterable"
                    content=entry.content[0]['value'] if entry.content else entry.description,
                )
                logger.info(f'  Added new article: {article.title}')
                # 注意这里的缩进，如果已经存在 Database 中的文章（非新文章），那么就不需要浪费 token 总结了
#            else:
#                article = existing_article
                if self.current_n_processed < feed.articles_to_summarize_per_interval and passes_filters(entry, feed, 'summary_filter'): # and not article.summarized:
                    self.generate_summary(article, feed.model, feed.summary_language)
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
            logger.info('  OpenAI API key or model not set, skipping summary generation')
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
            logger.info(f'  Summary generated for article: {article.title}')
            article.save()
        except Exception as e:
            logger.error(f'Failed to generate summary for article {article.title}: {str(e)}')