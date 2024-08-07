from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from FeedManager.models import ProcessedFeed, Article, Digest
from datetime import timedelta
import logging
from FeedManager.utils import generate_summary, clean_txt_and_truncate

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
                raise CommandError(f'ProcessedFeed with name {feed_name} does not exist.')
        else:
            processed_feeds = ProcessedFeed.objects.filter(toggle_digest=True)
            for feed in processed_feeds:
                if not feed.toggle_digest:
                    continue
                logger.info(f'Generating digest for feed: {feed.name} at {timezone.now()}')
                self.gen_digest(feed, force)

    def gen_digest(self, feed, force):
        now = timezone.now()
        last_digest = feed.last_digest
        # The cron job runs every 24 hours
        # Incase skip a day, we set delta to 0.5 days
        delta = timedelta(days=0.5) if feed.digest_frequency == 'daily' else timedelta(days=6.5)
        logger.debug(f"Last digest: {last_digest}")
        if force or (not last_digest) or now - last_digest > delta:
            if force or (not last_digest):
                start_time = now - delta - timedelta(days=0.5)
            else:
                start_time = last_digest
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
            for field in ['include_one_line_summary', 'include_summary', 'include_content', 'use_ai_digest', 'include_toc']:
                if getattr(feed, field):
                    what_to_include.append(field)
            logger.debug(f"  What to include: {what_to_include}")
            digest_content = self.format_digest(articles, what_to_include)
            digest = Digest(processed_feed=feed, content=digest_content, created_at=now, start_time=start_time)
            #digest.save()

            if 'use_ai_digest' in what_to_include:
                # Convert digest to article for AI processing
                digest_article = Article(
                    title=f"Digest for {feed.name} {digest.start_time.strftime('%Y-%m-%d %H:%M:%S')} to {digest.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
                    link=f"/admin/FeedManager/digest/{digest.id}/change/",
                    published_date=digest.created_at,
                    content=digest.content,
                    summarized=True
                )
                prompt = "These are the recent articles from the feed, please summarize important points in a paragragh, with summarized details, do not just make a list of the titles; when you mention a point, please reference to the original article url using HTML tag, please output result in {feed.summary_language} language."
                # Build up query for AI digest, by default includes title, link, and summaries
                query = ""
                for article in articles:
                    query += f"Title: {article.title}{article.link}\n"
                    if article.summary_one_line:
                        query += f"{article.summary_one_line}\n"
                    if article.summary:
                        query += f"Summary Long: {article.summary}\n"
                    if feed.send_full_article and article.content:
                        query += f"Full Content: {article.content}\n"
                query = clean_txt_and_truncate(query,model= feed.digest_model, clean_bool=True)
                # Generate a pseudo article for AI digest
                for_summary_only_article = Article(
                    title=f"Digest for {feed.name} {digest.start_time.strftime('%Y-%m-%d %H:%M:%S')} to {digest.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
                    link=f"/admin/FeedManager/digest/{digest.id}/change/",
                    published_date=digest.created_at,
                    content=query,
                    summarized=True
                )
                logger.debug(f"  Query for AI digest: {query}")
                if feed.additional_prompt_for_digest:
                    prompt = feed.additional_prompt_for_digest
                logger.info(f"  Using AI model {feed.digest_model} to generate digest.")
                digest_ai_result = generate_summary(for_summary_only_article, feed.digest_model, output_mode='HTML', prompt=prompt, other_model=feed.other_digest_model)
                logger.debug(f"  AI digest result: {digest_ai_result}")
                # prepend the AI digest result to the digest content
                if digest_ai_result:
                    format_digest_result = '' + digest_ai_result + '<br/>'
                    digest.content = '<h2>AI Digest</h2>' + format_digest_result + digest.content

            digest.save()
            logger.info(f"  Digest for {feed.name} created.")
            feed.last_digest = now
            feed.save()

    def format_digest(self, articles, what_to_include):
        current_feed = None
        digest_builder = []
        # Table of Content: ## Feed Title, - Article Title(URL) > One_line_summary
        if 'include_toc' in what_to_include or ('include_one_line_summary' in what_to_include and any(article.summary_one_line for article in articles)):
            digest_builder.append("<h2>Table of Content</h2>")
            for article in articles:
                if current_feed != article.original_feed:
                    if current_feed:
                        digest_builder.append("<br/>")
                    current_feed = article.original_feed
                    digest_builder.append(f"<h3><a href='{current_feed.url}'>{current_feed.title}</a></h3>")
                digest_builder.append(f"<li><a href='{article.link}'>{article.title}</a></li>")
                if article.summary_one_line:
                    digest_builder.append(f"{article.summary_one_line}")
                digest_builder.append("<br/>")
        # If content in what_to_include, or summary in what_to_include and there should be at least one summary
        # Details: ## Feed Title, - Article Title(URL) > Summary+Content
        if 'include_content' in what_to_include or ('include_summary' in what_to_include and any(article.summary for article in articles)):
            digest_builder.append("<br/>")
            digest_builder.append("<h2>Details</h2>")
            for article in articles:
                if current_feed != article.original_feed:
                    if current_feed:
                        digest_builder.append("</br>")
                    current_feed = article.original_feed
                    digest_builder.append(f"<h3><a href='{current_feed.url}'>{current_feed.title}</a></h3>")
                digest_builder.append(f"<li><a href='{article.link}'>{article.title}</a></li>")
                if 'include_toc' not in what_to_include and 'include_one_line_summary' in what_to_include and article.summary_one_line:
                    digest_builder.append(f"{article.summary_one_line}")
                if 'include_summary' in what_to_include and article.summary:
                    digest_builder.append(f"<br/>{article.summary}")
                if 'include_content' in what_to_include and article.content:
                    digest_builder.append(f"Content:<br/>{article.content}")
                digest_builder.append("<br/>")

        return ''.join(digest_builder)
