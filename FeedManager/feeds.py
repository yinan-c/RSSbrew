from django.contrib.syndication.views import Feed
from django.utils.feedgenerator import Rss201rev2Feed
from django.shortcuts import get_object_or_404, Http404
from django.http import HttpResponseForbidden
from .models import ProcessedFeed, Article, Filter, AppSetting
import re
from .utils import passes_filters, match_content, generate_untitled

class ProcessedAtomFeed(Feed):
    feed_type = Rss201rev2Feed

    def get_object(self, request, feed_id=None, feed_name=None):
        auth_code = request.GET.get('key', '')
        expected_code = AppSetting.get_auth_code()

        if expected_code and (not auth_code or auth_code != expected_code):
            raise Http404("You do not have permission to view this feed.")  # Raise Http404 instead of returning HttpResponseForbidden

        if feed_id:
            return get_object_or_404(ProcessedFeed, id=feed_id)
        elif feed_name:
            return get_object_or_404(ProcessedFeed, name=feed_name)

    def title(self, obj):
        return obj.name

    def link(self, obj):
        return f"/feeds/{obj.id}/"

    def description(self, obj):
        original_feeds = ', '.join([feed.url for feed in obj.feeds.all()])
        return f"Processed feed combining these original feeds: {original_feeds}, filtered by {', '.join([filter.field for filter in obj.filters.all()])}"

    def items(self, obj):
        articles = Article.objects.filter(original_feed__in=obj.feeds.all()).order_by('-published_date')
        filtered_articles = [article for article in articles if passes_filters(article, obj, 'feed_filter')]
        return filtered_articles

    def item_title(self, item):
        return item.title
    
    def item_pubdate(self, item):
        return item.published_date

    def item_description(self, item):
        # if there is no summary, use the content,
        # otherwise use the summary and content together
        description = item.content
        if item.summary:
            description = f"{item.summary} {description}"
        return description

    def item_link(self, item):
        # 直接返回文章的原始链接，假设每篇文章都有一个URL字段
        return item.url