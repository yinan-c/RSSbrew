from datetime import datetime

from django.db.models import Max
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


def digest_list_view(request, feed_name):
    """Display a list of all digests for a feed, grouped by date."""
    # Get the processed feed by name
    processed_feed = get_object_or_404(ProcessedFeed, name=feed_name)

    # Check if authentication is required
    auth_code = AppSetting.get_auth_code()
    if auth_code:
        provided_key = request.GET.get("key")
        if provided_key != auth_code:
            raise Http404("Invalid authentication key")

    # Get all digests for this feed, grouped by date
    # If multiple digests exist for the same date, we'll use the latest one
    digests = (
        Digest.objects.filter(processed_feed=processed_feed)
        .values("created_at__date")
        .annotate(latest_created_at=Max("created_at"))
        .order_by("-created_at__date")
    )

    # Get the actual digest objects for display
    digest_list = []
    for digest_date in digests:
        date = digest_date["created_at__date"]
        latest_digest = (
            Digest.objects.filter(processed_feed=processed_feed, created_at__date=date).order_by("-created_at").first()
        )
        if latest_digest:
            digest_list.append(
                {
                    "date": date,
                    "date_str": date.strftime("%Y-%m-%d"),
                    "digest": latest_digest,
                    "date_range": (
                        f"{latest_digest.start_time.strftime('%Y-%m-%d %H:%M')} - {latest_digest.created_at.strftime('%Y-%m-%d %H:%M')}"
                        if latest_digest.start_time
                        else f"Until {latest_digest.created_at.strftime('%Y-%m-%d %H:%M')}"
                    ),
                }
            )

    context = {
        "feed_name": processed_feed.name,
        "feed_id": processed_feed.id,
        "digest_list": digest_list,
        "auth_key": f"?key={auth_code}" if auth_code else "",
    }

    return render(request, "FeedManager/digest_list.html", context)
