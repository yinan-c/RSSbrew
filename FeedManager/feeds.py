from django.contrib.syndication.views import Feed
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.feedgenerator import Rss201rev2Feed

from .models import AppSetting, Article, ProcessedFeed
from .utils import passes_filters, remove_control_characters


class ProcessedAtomFeed(Feed):
    feed_type = Rss201rev2Feed

    def get_object(self, request, feed_id=None, feed_name=None):
        auth_code = request.GET.get("key", "")
        expected_code = AppSetting.get_auth_code()

        if expected_code and (not auth_code or auth_code != expected_code):
            raise Http404(
                "You do not have permission to view this feed."
            )  # Raise Http404 instead of returning HttpResponseForbidden

        if feed_id:
            return get_object_or_404(ProcessedFeed, id=feed_id)
        elif feed_name:
            return get_object_or_404(ProcessedFeed, name=feed_name)

    def title(self, obj):
        return obj.name

    def link(self, obj):
        # url = reverse('processed_feed_by_id', args=[obj.id])
        # url = f"/feeds/{obj.name}/"
        url = reverse("processed_feed_by_name", args=[obj.name])
        auth_code = AppSetting.get_auth_code()  # Get the universal auth code
        if not auth_code:
            return url
        return f"{url}?key={auth_code}"

    def feed_url(self, obj):
        return self.link(obj)

    def description(self, obj):
        original_feeds = ", ".join([feed.url for feed in obj.feeds.all()])
        return f"Processed feed combining these original feeds: {original_feeds}, with {obj.filter_groups.count()} filter groups. All rights of the content belong to the original authors."

    def items(self, obj):
        result_items = []
        if obj.toggle_digest:
            # Get the most recent digest
            digest = obj.digests.order_by("-created_at").first()
            if digest:
                digest_article = Article(
                    title=f"Digest for {obj.name} {digest.start_time.strftime('%Y-%m-%d %H:%M:%S')} to {digest.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
                    link=f"/admin/FeedManager/digest/{digest.id}/change/",
                    published_date=digest.created_at,
                    content=digest.content,
                    summarized=True,
                    custom_prompt=True,
                )
                result_items.append(digest_article)

        if obj.toggle_entries:
            articles = Article.objects.filter(original_feed__in=obj.feeds.all()).order_by("-published_date")

            filtered_articles = [article for article in articles if passes_filters(article, obj, "feed_filter")]

            seen = set()
            unique_articles = []
            for article in filtered_articles:
                # URL is already cleaned in database, no need to clean again
                identifier = article.link
                if identifier not in seen:
                    seen.add(identifier)
                    unique_articles.append(article)
            result_items.extend(unique_articles)

        return result_items

    def item_title(self, item):
        return remove_control_characters(item.title)

    def item_pubdate(self, item):
        return item.published_date

    def item_description(self, item):
        # if there is no summary, use the content,
        # otherwise use the summary and content together
        description = remove_control_characters(item.content)
        if item.summary:
            formatted_summary = f"{item.summary}<br/>"
            description = f"<br/><br/>{formatted_summary}<br/>Original Content:<br/>{item.content}"
        if item.summary_one_line:
            description = f"{item.summary_one_line}<br/>{description}"
        return description

    def item_link(self, item):
        # Return the article's original link directly
        return item.link
