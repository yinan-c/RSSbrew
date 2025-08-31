from django.urls import path

from .feeds import ProcessedAtomFeed
from .views import digest_html_view

urlpatterns = [
    path("<int:feed_id>/", ProcessedAtomFeed(), name="processed_feed_by_id"),
    path("<str:feed_name>/", ProcessedAtomFeed(), name="processed_feed_by_name"),
    path("<str:feed_name>/digest/", digest_html_view, name="digest_html"),
]
