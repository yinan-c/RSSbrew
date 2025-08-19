from django.core.management import CommandError
from django.core.management.base import BaseCommand

from FeedManager.models import Article, OriginalFeed


class Command(BaseCommand):
    help = 'Cleans up old articles from the database to maintain a maximum limit per feed.'

    def add_arguments(self, parser):
        parser.add_argument('-f', '--feed', type=int, help='ID of the OriginalFeed to clean')

    def handle(self, *args, **options):
        feed_id = options.get('feed')
        if feed_id:
            try:
                feed = OriginalFeed.objects.get(id=feed_id)
                self.clean_feed_articles(feed)
            except OriginalFeed.DoesNotExist:
                raise CommandError(f'OriginalFeed "{feed_id}" does not exist')
        else:
            feeds = OriginalFeed.objects.all()
            for feed in feeds:
                self.clean_feed_articles(feed)

    def clean_feed_articles(self, feed):
        article_count = Article.objects.filter(original_feed=feed).count()
        if article_count > feed.max_articles_to_keep:
            excess = article_count - feed.max_articles_to_keep
            articles_to_delete_ids = Article.objects.filter(original_feed=feed).order_by('published_date').values_list('id', flat=True)[:excess]
            Article.objects.filter(id__in=list(articles_to_delete_ids)).delete()
            self.stdout.write(self.style.SUCCESS(f'Deleted {excess} old articles from feed {feed.title}'))
