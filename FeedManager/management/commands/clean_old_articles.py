from django.core.management.base import BaseCommand
from FeedManager.models import OriginalFeed, Article
from django.db.models import Count

class Command(BaseCommand):
    help = 'Cleans up old articles from the database to maintain a maximum limit per feed.'

    def handle(self, *args, **options):
        for feed in OriginalFeed.objects.all():
            # 计算当前 feed 的文章数量是否超过限制
            article_count = Article.objects.filter(original_feed=feed).count()
            if article_count > feed.max_articles_to_keep:
                # 计算超出的数量
                excess = article_count - feed.max_articles_to_keep
                # 获取最旧的 excess 篇文章的 ID
                articles_to_delete_ids = Article.objects.filter(original_feed=feed).order_by('published_date').values_list('id', flat=True)[:excess]
                # 使用 ID 列表执行删除操作
                Article.objects.filter(id__in=list(articles_to_delete_ids)).delete()
                self.stdout.write(self.style.SUCCESS(f'Deleted {excess} old articles from feed {feed.title}'))
