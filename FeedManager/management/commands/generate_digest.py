from django.core.management.base import BaseCommand
from django.utils import timezone
from FeedManager.models import ProcessedFeed, Article, Digest
from datetime import timedelta
import logging

logger = logging.getLogger('feed_logger')

class Command(BaseCommand):
    help = 'Generate digest for each processed feed.'

    def add_arguments(self, parser):
        parser.add_argument('-n', '--name', type=str, help='Name of the ProcessedFeed to update')
        parser.add_argument('--force', action='store_true', help='Force digest generation for all feeds')

    def handle(self, *args, **options):
        feed_name = options.get('name')
        force = options.get('force')
        if feed_name:
            try:
                feed = ProcessedFeed.objects.get(name=feed_name)
                logger.info(f'Generating digest for feed: {feed.name} at {timezone.now()}')
                # if feed.toggle_digest: # This will disble force digest generation for a selected feed
                self.gen_digest(feed, force)
            except ProcessedFeed.DoesNotExist:
                raise CommandError(f'ProcessedFeed with ID {feed_id} does not exist.')
        else:
            processed_feeds = ProcessedFeed.objects.filter(toggle_digest=True)
            for feed in processed_feeds:
                logger.info(f'Generating digest for feed: {feed.name} at {timezone.now()}')
                self.gen_digest(feed, force)

    def gen_digest(self, feed, force):
        now = timezone.now()
        last_digest = feed.last_digest
        # The cron job runs every 24 hours
        # Incase skip a day, we set delta to 0.5 days
        delta = timedelta(days=0.5) if feed.digest_frequency == 'daily' else timedelta(days=6.5)
        logger.debug(f"Last digest: {last_digest}")
        if force or not last_digest or now - last_digest > delta:
            if force:
                start_time = now - delta - timedelta(days=0.5)
            else:
                start_time = last_digest if last_digest else now - delta - timedelta(days=0.5)
            articles = Article.objects.filter(
                original_feed__processed_feeds=feed,
                published_date__gte=start_time,
                published_date__lte=now
            ).order_by('original_feed', '-published_date')
#            logger.debug(f"  Found {articles.count()} articles for feed {feed.name}")
#            logger.debug(articles[0].summary_one_line)
            if not articles.exists():
                logger.info(f"  No new articles for feed {feed.name} since last digest.")
                return
            what_to_include = []
            for field in ['include_one_line_summary', 'include_summary', 'include_content', 'use_ai_digest']:
                if getattr(feed, field):
                    what_to_include.append(field)
            logger.debug(f"  What to include: {what_to_include}")
            digest_content = self.format_digest(articles, what_to_include)
            digest = Digest(processed_feed=feed, content=digest_content, created_at=now, start_time=start_time)
            digest.save()
            logger.info(f"  Digest for {feed.name} created.")
            feed.last_digest = now
            feed.save()

    def format_digest(self, articles, what_to_include):
        current_feed = None
        digest_builder = []
        # Table of Content: ## Feed Title, - Article Title(URL) > One_line_summary
        digest_builder.append("<h2>Table of Content</h2>")
        for article in articles:
            if current_feed != article.original_feed:
                if current_feed:
                    digest_builder.append("<br>")
                current_feed = article.original_feed
                digest_builder.append(f"<h3><a href='{current_feed.url}'>{current_feed.title}</a></h3>")
            digest_builder.append(f"<li><a href='{article.url}'>{article.title}</a></li>")
            if 'include_one_line_summary' in what_to_include and article.summary_one_line:
                digest_builder.append(f"<ul><blockquote>{article.summary_one_line}</blockquote></ul>")
            digest_builder.append("<br>")
        # If content in what_to_include, or summary in what_to_include, then inlude Details
        # Details: ## Feed Title, - Article Title(URL) > Summary+Content
        if 'include_content' in what_to_include or 'include_summary' in what_to_include:
            digest_builder.append("<br>")
            digest_builder.append("<h2>Details</h2>")
            for article in articles:
                if current_feed != article.original_feed:
                    if current_feed:
                        digest_builder.append("</br>")
                    current_feed = article.original_feed
                    digest_builder.append(f"<h3><a href='{current_feed.url}'>{current_feed.title}</a></h3>")
                digest_builder.append(f"<li><a href='{article.url}'>{article.title}</a></li>")
                if 'include_summary' in what_to_include and article.summary:
                    digest_builder.append(f"<ul>Summary:<br><blockquote>{article.summary}</blockquote></ul>")
                if 'include_content' in what_to_include and article.content:
                    digest_builder.append(f"<ul>Content:<br>{article.content}</ul>")
                digest_builder.append("<br>")

        return ''.join(digest_builder)
