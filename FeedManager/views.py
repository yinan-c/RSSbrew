from django.http import Http404
from django.shortcuts import get_object_or_404, render

from .models import AppSetting, Digest


def digest_html_view(request, digest_id):
    """Serve digest content as an HTML page with optional authentication."""
    digest = get_object_or_404(Digest, id=digest_id)

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
        "date_range": date_range,
    }

    return render(request, "FeedManager/digest.html", context)
