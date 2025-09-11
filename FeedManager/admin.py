from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, tostring

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django.contrib.auth.models import Group, User
from django.db.models import Count
from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

import pytz
from defusedxml import minidom
from nested_admin.nested import NestedModelAdmin, NestedTabularInline

from .forms import FilterForm, OPMLUploadForm, ProcessedFeedAdminForm, ReadOnlyArticleForm
from .models import AppSetting, Article, Digest, Filter, FilterGroup, OriginalFeed, ProcessedFeed, Tag
from .opml import (
    export_original_feeds_as_opml as build_original_feeds_opml,
)
from .opml import (
    import_original_feeds_from_opml,
)
from .tasks import async_update_feeds_and_digest, clean_old_articles


@admin.action(description=_("Update selected feeds"))
def update_selected_feeds(modeladmin, request, queryset):
    for feed in queryset:
        async_update_feeds_and_digest(feed.name)
        # If you select a feed to update, you are forcely generating a digest for it
        modeladmin.message_user(
            request, _("Feed update tasks have been queued for feed: %(feed_name)s") % {"feed_name": feed.name}
        )


@admin.action(description=_("Clean old articles for selected feeds"))
def clean_selected_feeds_articles(modeladmin, request, queryset):
    for feed in queryset:
        clean_old_articles(feed.id)
        modeladmin.message_user(
            request, _("Cleaned old articles from feed: %(feed_title)s") % {"feed_title": feed.title}
        )


@admin.action(description=_("Export selected feeds as OPML"))
def export_original_feeds_as_opml(modeladmin, request, queryset):
    """Export selected original feeds as a flat OPML (with categories)."""
    xml_string = build_original_feeds_opml(queryset, group_by_tags=False)
    response = HttpResponse(xml_string, content_type="text/xml; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="rssbrew_original_feeds_{datetime.now().strftime("%Y%m%d_%H%M%S")}.opml"'
    )
    return response


@admin.action(description=_("Export selected feeds as OPML (grouped by tags)"))
def export_original_feeds_as_opml_grouped(modeladmin, request, queryset):
    """Export selected original feeds grouped under tag folders."""
    xml_string = build_original_feeds_opml(queryset, group_by_tags=True)
    response = HttpResponse(xml_string, content_type="text/xml; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="rssbrew_original_feeds_grouped_{datetime.now().strftime("%Y%m%d_%H%M%S")}.opml"'
    )
    return response


@admin.action(description=_("Export selected feeds as OPML"))
def export_processed_feeds_as_opml(modeladmin, request, queryset):
    """Export selected processed feeds as OPML"""
    # Create OPML structure
    opml = Element("opml")
    opml.set("version", "2.0")

    # Create head section
    head = SubElement(opml, "head")
    title = SubElement(head, "title")
    title.text = "RSSBrew Processed Feeds Export"
    date_created = SubElement(head, "dateCreated")
    tz = pytz.timezone(getattr(settings, "TIME_ZONE", "UTC"))
    date_created.text = datetime.now(tz).strftime("%a, %d %b %Y %H:%M:%S %z")

    # Create body section
    body = SubElement(opml, "body")

    # Add each processed feed as an outline
    for processed_feed in queryset:
        outline = SubElement(body, "outline")
        outline.set("text", processed_feed.name)
        outline.set("title", processed_feed.name)
        outline.set("type", "rss")

        # Generate the processed feed URL (same as Subscribe link)
        processed_url = request.build_absolute_uri(reverse("processed_feed_by_name", args=[processed_feed.name]))
        auth_code = AppSetting.get_auth_code()
        if auth_code:
            processed_url += f"?key={auth_code}"
        outline.set("xmlUrl", processed_url)
        outline.set("htmlUrl", processed_url)

    # Convert to pretty XML string
    xml_string = minidom.parseString(tostring(opml, encoding="unicode")).toprettyxml(indent="  ")

    # Create HTTP response with OPML content
    response = HttpResponse(xml_string, content_type="text/xml; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="rssbrew_processed_feeds_{datetime.now().strftime("%Y%m%d_%H%M%S")}.opml"'
    )

    return response


class FilterInline(NestedTabularInline):
    model = Filter
    form = FilterForm
    extra = 0


class FilterGroupInline(NestedTabularInline):
    model = FilterGroup
    inlines = [FilterInline]
    extra = 0


class ArticleInline(admin.TabularInline):
    model = Article
    form = ReadOnlyArticleForm
    extra = 0
    readonly_fields = [field.name for field in Article._meta.fields if field.name != "content"]
    classes = ["collapse"]  # Make the inline collapsed by default

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class HasAnyOriginalFeedListFilter(admin.SimpleListFilter):
    title = _("Has any original feed")
    parameter_name = "has_any_original_feed"

    def lookups(self, request, model_admin):
        return (
            ("yes", _("Yes")),
            ("no", _("No")),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.exclude(feeds=None)
        if self.value() == "no":
            return queryset.filter(feeds=None)


class HasIncludedTagsFilter(admin.SimpleListFilter):
    title = _("Has included tags")
    parameter_name = "has_included_tags"

    def lookups(self, request, model_admin):
        return (
            ("yes", _("Yes")),
            ("no", _("No")),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.exclude(include_tags=None)
        if self.value() == "no":
            return queryset.filter(include_tags=None)


@admin.register(ProcessedFeed)
class ProcessedFeedAdmin(NestedModelAdmin):
    form = ProcessedFeedAdminForm
    inlines = [FilterGroupInline]

    # rename articles_to_summarize_per_interval to Summarize per Update in list display
    @admin.display(description=_("Summarize per Update"), ordering="articles_to_summarize_per_interval")
    def summarize_per_update(self, obj):
        return obj.articles_to_summarize_per_interval

    @admin.display(description=_("Digest/Entries"))
    def toggle_digest_and_update(self, obj):
        # An emoji description to show if the digest/entries are enabled
        # Use 🤖 robot emoji when AI digest is enabled, otherwise ✅
        digest_emoji = "🤖" if obj.toggle_digest and obj.use_ai_digest else ("✅" if obj.toggle_digest else "❌")
        entries_emoji = "✅" if obj.toggle_entries else "❌"
        return f"{digest_emoji}/{entries_emoji}"

    list_display = (
        "name",
        "summarize_per_update",
        "subscription_link",
        "original_feed_count",
        "total_feed_count",
        "toggle_digest_and_update",
    )
    #    filter_horizontal = ('feeds',)
    search_fields = ("name", "feeds__title", "feeds__url", "include_tags__name")
    list_filter = (
        "articles_to_summarize_per_interval",
        "summary_language",
        "model",
        HasAnyOriginalFeedListFilter,
        HasIncludedTagsFilter,
        "toggle_digest",
        "toggle_entries",
        "digest_frequency",
        "use_ai_digest",
        "digest_model",
    )
    actions = [update_selected_feeds, export_processed_feeds_as_opml]
    autocomplete_fields = ["feeds", "include_tags"]

    def get_queryset(self, request):
        # Annotate each ProcessedFeed object with the count of related OriginalFeeds
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(_original_feed_count=Count("feeds"))
        return queryset

    @admin.display(
        description=_("Direct Feeds"),
        ordering="_original_feed_count",
    )
    def original_feed_count(self, obj):
        # Use the annotated count of directly selected OriginalFeeds
        return obj._original_feed_count

    @admin.display(
        description=_("Total Feeds"),
    )
    def total_feed_count(self, obj):
        # Get all feeds including those from tags
        all_feeds = obj.get_all_feeds()
        return len(all_feeds)

    fieldsets = (
        (
            None,
            {
                "fields": ("name", "feeds", "include_tags"),
                "description": _(
                    "Select specific feeds to include, or choose tags to automatically include all feeds with those tags. "
                    "⚠️ At least one feed or tag must be selected."
                ),
            },
        ),
        (
            _("Filter Settings"),
            {
                "fields": ("feed_group_relational_operator", "case_sensitive"),
                "description": _(
                    "Configure filter groups at the end. The logic operator determines how multiple filter groups are combined."
                ),
            },
        ),
        (
            _("Summarization Options"),
            {
                "fields": (
                    "summary_group_relational_operator",
                    "articles_to_summarize_per_interval",
                    "summary_language",
                    "translate_title",
                    "model",
                    "other_model",
                    "additional_prompt",
                ),
            },
        ),
        (
            _("Digest Options"),
            {
                "fields": (
                    "toggle_entries",
                    "toggle_digest",
                    "digest_frequency",
                    "last_digest",
                ),  # , 'include_one_line_summary', 'include_summary', 'include_content',  'use_ai_digest', 'digest_model', 'additional_prompt_for_digest','send_full_article'),
            },
        ),
        (
            _("What to include in digest"),
            {
                "fields": (
                    "include_toc",
                    "include_one_line_summary",
                    "include_summary",
                    "include_content",
                    "use_ai_digest",
                    "digest_model",
                    "other_digest_model",
                    "additional_prompt_for_digest",
                    "send_full_article",
                ),
            },
        ),
    )

    @admin.display(description=_("Subscribe Link"))
    def subscription_link(self, obj):
        url = reverse("processed_feed_by_name", args=[obj.name])
        auth_code = AppSetting.get_auth_code()  # Get the universal auth code
        if not auth_code:
            return format_html('<a href="{}">Subscribe</a>', url)
        return format_html('<a href="{}?key={}">Subscribe</a>', url, auth_code)

    # Including JavaScript for dynamic form behavior
    class Media:
        js = (
            "js/admin/toggle_digest_fields.js",
            "js/admin/toggle_ai_digest_fields.js",
        )


class IncludedInProcessedFeedListFilter(admin.SimpleListFilter):
    title = _("Included in processed feeds")
    parameter_name = "included_in_processed_feed"

    def lookups(self, request, model_admin):
        return (
            ("yes", _("Yes")),
            ("no", _("No")),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(processed_feeds__isnull=False).distinct()
        if self.value() == "no":
            return queryset.filter(processed_feeds__isnull=True)

class OriginalFeedActionForm(ActionForm):
    tag_names = forms.CharField(
        required=False,
        label=_("Tags"),
        help_text=_("Comma-separated. Used by add/remove tag actions."),
        widget=forms.TextInput(
            attrs={
                "placeholder": _("e.g. Tech, News"),
                "list": "tag-names-datalist",
                "autocomplete": "off",
            }
        ),
    )


@admin.register(OriginalFeed)
class OriginalFeedAdmin(admin.ModelAdmin):
    inlines = [ArticleInline]
    list_display = ("title", "valid", "url", "tags_list", "processed_feeds_count")
    search_fields = ("title", "url", "tags__name")
    action_form = OriginalFeedActionForm

    def get_queryset(self, request):
        # Annotate each OriginalFeed object with the count of related ProcessedFeeds
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(_processed_feeds_count=Count("processed_feeds")).prefetch_related("tags")
        return queryset

    @admin.display(
        description=_("Processed Feeds"),
        ordering="_processed_feeds_count",
    )
    def processed_feeds_count(self, obj):
        # Use the annotated count of related ProcessedFeeds
        return obj._processed_feeds_count

    # Filter if the original feed is included in the processed feed
    list_filter = ("valid", "processed_feeds__name", IncludedInProcessedFeedListFilter, "tags")
    actions = [
        "action_add_tags",
        "action_remove_tags",
        clean_selected_feeds_articles,
        export_original_feeds_as_opml,
        export_original_feeds_as_opml_grouped,
    ]
    autocomplete_fields = ["tags"]

    @admin.display(description=_("Tags"))
    def tags_list(self, obj):
        names = list(obj.tags.values_list("name", flat=True))
        return ", ".join(sorted(names, key=str.casefold)) if names else "-"

    @admin.action(description=_("Add tags to selected feeds"))
    def action_add_tags(self, request, queryset):
        raw_names = (request.POST.get("tag_names") or "").strip()
        if not raw_names:
            self.message_user(
                request,
                _("Please provide tag names in the action bar (comma-separated)."),
                level=messages.WARNING,
            )
            return None

        # Split by comma/semicolon, normalize spacing
        import re as _re

        names = [_n.strip() for _n in _re.split(r"[;,]", raw_names) if _n.strip()]
        if not names:
            self.message_user(
                request,
                _("No valid tag names detected. Please enter comma-separated names."),
                level=messages.WARNING,
            )
            return None

        created = 0
        from .models import Tag

        tag_objs = []
        for name in names:
            tag, is_created = Tag.objects.get_or_create(name=name)
            if is_created:
                created += 1
            tag_objs.append(tag)

        updated_feeds = 0
        for feed in queryset:
            # add without duplication
            for tag in tag_objs:
                feed.tags.add(tag)
            updated_feeds += 1

        self.message_user(
            request,
            _("Added %(tag_count)d tag(s) (%(created)d new) to %(feed_count)d feed(s).")
            % {"tag_count": len(tag_objs), "created": created, "feed_count": updated_feeds},
            level=messages.SUCCESS,
        )
        return None

    @admin.action(description=_("Remove tags from selected feeds"))
    def action_remove_tags(self, request, queryset):
        raw_names = (request.POST.get("tag_names") or "").strip()
        if not raw_names:
            self.message_user(
                request,
                _("Please provide tag names in the action bar (comma-separated)."),
                level=messages.WARNING,
            )
            return None

        import re as _re

        names = [_n.strip() for _n in _re.split(r"[;,]", raw_names) if _n.strip()]
        if not names:
            self.message_user(
                request,
                _("No valid tag names detected. Please enter comma-separated names."),
                level=messages.WARNING,
            )
            return None

        from .models import Tag

        tags = list(Tag.objects.filter(name__in=names))
        not_found = sorted(set(names) - {t.name for t in tags}, key=str.casefold)

        removed_links = 0
        for feed in queryset:
            for tag in tags:
                if feed.tags.filter(pk=tag.pk).exists():
                    feed.tags.remove(tag)
                    removed_links += 1

        msg = _("Removed %(removed)d tag assignment(s) from %(feed_count)d feed(s).") % {
            "removed": removed_links,
            "feed_count": queryset.count(),
        }
        if not_found:
            msg += " " + _("Tags not found: %(names)s") % {"names": ", ".join(not_found)}
        self.message_user(request, msg, level=messages.SUCCESS)
        return None

    # Custom admin view: Import OPML
    def get_urls(self):
        from django.urls import path

        urls = super().get_urls()
        custom_urls = [
            path(
                "import-opml/",
                self.admin_site.admin_view(self.import_opml_view),
                name="FeedManager_originalfeed_import_opml",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        from django.urls import reverse

        extra_context = extra_context or {}
        extra_context["import_opml_url"] = reverse("admin:FeedManager_originalfeed_import_opml")
        # Provide tag names to power the datalist suggestions for the action form
        extra_context["all_tag_names"] = list(Tag.objects.order_by("name").values_list("name", flat=True))
        return super().changelist_view(request, extra_context=extra_context)

    def import_opml_view(self, request):
        from django.contrib import messages
        from django.shortcuts import redirect, render
        from django.urls import reverse

        if request.method == "POST":
            form = OPMLUploadForm(request.POST, request.FILES)
            if form.is_valid():
                file = form.cleaned_data["opml_file"]
                # Quick format check before parsing to warn for wrong uploads (e.g., Markdown)
                try:
                    from codecs import BOM_UTF8
                    from contextlib import suppress

                    head = file.read(2048)
                    # Normalize to bytes
                    head_bytes = head.encode("utf-8", errors="ignore") if isinstance(head, str) else head
                    # Strip BOM and leading whitespace
                    if head_bytes.startswith(BOM_UTF8):
                        head_bytes = head_bytes[len(BOM_UTF8) :]
                    head_str = head_bytes.decode("utf-8", errors="ignore").lstrip().lower()

                    content_type = getattr(file, "content_type", "") or ""
                    looks_xml = "xml" in content_type or "opml" in content_type or "<opml" in head_str
                finally:
                    # Reset pointer regardless of outcome
                    with suppress(Exception):
                        file.seek(0)

                if not looks_xml:
                    messages.error(
                        request,
                        _(
                            "The uploaded file does not look like an OPML/XML file. Please upload a valid OPML export."
                        ),
                    )
                    context = dict(
                        self.admin_site.each_context(request),
                        title=_("Import Original Feeds from OPML"),
                        form=form,
                    )
                    return render(request, "admin/FeedManager/originalfeed/import_opml.html", context)

                # Proceed with import
                result = import_original_feeds_from_opml(file)
                messages.success(
                    request,
                    _(
                        "Imported OPML: %(seen)d feeds parsed; %(created)d created; %(updated)d touched; %(tags)d new tags"
                    )
                    % {
                        "seen": result.feeds_seen,
                        "created": result.feeds_created,
                        "updated": result.feeds_updated,
                        "tags": result.tags_created,
                    },
                )
                return redirect(reverse("admin:FeedManager_originalfeed_changelist"))
        else:
            form = OPMLUploadForm()

        context = dict(
            self.admin_site.each_context(request),
            title=_("Import Original Feeds from OPML"),
            form=form,
        )
        return render(request, "admin/FeedManager/originalfeed/import_opml.html", context)


@admin.register(AppSetting)
class AppSettingAdmin(admin.ModelAdmin):
    list_display = ["auth_code", "global_summary_model", "global_digest_model", "max_articles_per_feed"]
    fieldsets = (
        (
            _("Authentication"),
            {
                "fields": ("auth_code",),
            },
        ),
        (
            _("Global AI Model Settings"),
            {
                "fields": (
                    "global_summary_model",
                    "global_other_summary_model",
                    "global_digest_model",
                    "global_other_digest_model",
                ),
                "description": _(
                    "These settings will be used as defaults for all feeds unless overridden individually"
                ),
            },
        ),
        (
            _("Feed Settings"),
            {
                "fields": ("max_articles_per_feed",),
            },
        ),
    )

    def has_add_permission(self, request):
        """Only allow adding if no AppSetting exists"""
        return not AppSetting.objects.exists()

    def changelist_view(self, request, extra_context=None):
        """Redirect to change view if an instance exists, otherwise to add view"""
        from django.shortcuts import redirect
        from django.urls import reverse

        if AppSetting.objects.exists():
            instance = AppSetting.objects.first()
            if instance:  # Type guard for mypy
                return redirect(reverse("admin:FeedManager_appsetting_change", args=[instance.pk]))

        return redirect(reverse("admin:FeedManager_appsetting_add"))

    def response_add(self, request, obj, post_url_continue=None):
        """After adding, redirect to change view (since only one instance allowed)"""
        from django.shortcuts import redirect
        from django.urls import reverse

        return redirect(reverse("admin:FeedManager_appsetting_change", args=[obj.pk]))


admin.site.unregister(User)
admin.site.unregister(Group)


class OriginalFeedInline(admin.TabularInline):
    model = OriginalFeed.tags.through
    extra = 0


class HasAnyOriginalFeedListFilterTag(admin.SimpleListFilter):
    title = _("Has any original feed")
    parameter_name = "has_any_original_feed"

    def lookups(self, request, model_admin):
        return (
            ("yes", _("Yes")),
            ("no", _("No")),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.exclude(original_feeds=None)
        if self.value() == "no":
            return queryset.filter(original_feeds=None)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        # Annotate each Tag object with the count of related OriginalFeeds
        queryset = super().get_queryset(request)
        # Explicitly add ordering to prevent UnorderedObjectListWarning
        queryset = queryset.annotate(_original_feed_count=Count("original_feeds")).order_by("name")
        return queryset

    @admin.display(ordering="_original_feed_count")
    def original_feed_count(self, obj):
        # Use the annotated count of related OriginalFeeds
        return obj._original_feed_count

    list_display = ["name", "original_feed_count"]
    list_filter = [HasAnyOriginalFeedListFilterTag]
    inlines = [OriginalFeedInline]
    search_fields = ["name"]


@admin.register(Digest)
class DigestAdmin(admin.ModelAdmin):
    list_display = ["processed_feed", "created_at", "start_time"]
    search_fields = ["processed_feed__name"]
    readonly_fields = ["view_digest_button"]

    @admin.display(description="View Digest")
    def view_digest_button(self, obj):
        """Add a button to view the digest HTML page"""
        if obj.pk:
            from django.utils.html import format_html

            from .models import AppSetting

            auth_code = AppSetting.get_auth_code()
            url = f"/feeds/{obj.processed_feed.name}/digest/{obj.created_at.strftime('%Y-%m-%d')}/"
            if auth_code:
                url += f"?key={auth_code}"

            return format_html(
                '<a href="{}" target="_blank">View Digest Page</a>',
                url,
            )
        return "-"

    def get_fields(self, request, obj=None):
        """Override to place the view button at the top of the form"""
        fields = super().get_fields(request, obj)
        if obj:  # Only show button when editing existing digest
            # Place view_digest_button at the beginning
            return ["view_digest_button"] + [f for f in fields if f != "view_digest_button"]
        return fields
