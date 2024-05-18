from django.urls import path
from .feeds import ProcessedAtomFeed

urlpatterns = [
    path('<int:feed_id>/', ProcessedAtomFeed(), name='processed_feed_by_id'),
    path('<str:feed_name>/', ProcessedAtomFeed(), name='processed_feed_by_name'),
]