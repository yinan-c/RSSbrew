from datetime import datetime

from django.http import Http404
from django.shortcuts import get_object_or_404, render

from .models import AppSetting, Digest, ProcessedFeed


def digest_html_view(request, feed_name, date_str):
    """Serve digest content as an HTML page with optional authentication."""
    # Get the processed feed by name
    processed_feed = get_object_or_404(ProcessedFeed, name=feed_name)

    # Parse the date string (format: YYYY-MM-DD)
    try:
        digest_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise Http404("Invalid date format") from None

    # Get the digest for this feed and date
    digest = Digest.objects.filter(processed_feed=processed_feed, created_at__date=digest_date).first()

    if not digest:
        raise Http404("No digest found for this feed and date")

    # Check if authentication is required
    auth_code = AppSetting.get_auth_code()
    if auth_code:
        provided_key = request.GET.get("key")
        if provided_key != auth_code:
            raise Http404("Invalid authentication key")

    # Format the digest date range for display
    date_range = ""
    if digest.start_time and digest.created_at:
        date_range = f"{digest.start_time.strftime('%Y-%m-%d %H:%M')} - {digest.created_at.strftime('%Y-%m-%d %H:%M')}"
    elif digest.created_at:
        date_range = f"Until {digest.created_at.strftime('%Y-%m-%d %H:%M')}"

    context = {
        "digest": digest,
        "feed_name": digest.processed_feed.name,
        "feed_id": digest.processed_feed.id,
        "date_range": date_range,
    }

    return render(request, "FeedManager/digest.html", context)
