import re
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from .tasks import async_update_feeds_and_digest

if TYPE_CHECKING:
    from django.db.models import ManyToManyField

# Hardcoded fallback model when nothing is configured
DEFAULT_MODEL = "gpt-5-nano"

# Base model choices without "Use Global Setting"
BASE_MODEL_CHOICES = [
    ("gpt-5-mini", "GPT-5 Mini"),
    ("gpt-5-nano", "GPT-5 Nano"),
    ("gpt-5", "GPT-5"),
    ("gpt-4.1-mini", "GPT-4.1 Mini"),
    ("gpt-4.1-nano", "GPT-4.1 Nano"),
    ("gpt-4.1", "GPT-4.1"),
    ("gpt-4o-mini", "GPT-4o Mini"),
    ("gpt-4o", "GPT-4o"),
    ("gpt-4-turbo", "GPT-4 Turbo"),
    ("gpt-3.5-turbo", "GPT-3.5 Turbo"),
    ("other", _("Other (specify below)")),
]

# Global model choices (for AppSetting) - includes "None" option
GLOBAL_MODEL_CHOICES = [("none", _("None - Disable AI Features Globally")), *BASE_MODEL_CHOICES]

# Feed model choices (for ProcessedFeed) - includes "Use Global Setting"
MODEL_CHOICES = [("use_global", _("Use Global Setting")), *BASE_MODEL_CHOICES]


class AppSetting(models.Model):
    auth_code = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        verbose_name=_("Auth Code"),
        help_text=_("Optional authentication code to access RSS feeds"),
    )

    # Global AI model settings
    global_summary_model = models.CharField(
        max_length=255,
        default="none",
        choices=GLOBAL_MODEL_CHOICES,
        verbose_name=_("Global Summary Model"),
        help_text=_(
            "Master switch for AI summarization. "
            "When set to 'None', ALL AI summaries are disabled system-wide, regardless of individual feed settings. "
            "When set to a model, it enables AI features and serves as the default for feeds using 'Use Global Setting'."
        ),
    )
    global_other_summary_model = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=_("Specify model name if 'Other' is selected above, e.g. 'grok-3' in xAI"),
        verbose_name=_("Global Other Summary Model"),
    )
    global_digest_model = models.CharField(
        max_length=255,
        default="none",
        choices=GLOBAL_MODEL_CHOICES,
        verbose_name=_("Global Digest Model"),
        help_text=_(
            "Master switch for AI digest generation. "
            "When set to 'None', ALL AI digests are disabled system-wide, regardless of individual feed settings. "
            "When set to a model, it enables AI features and serves as the default for feeds using 'Use Global Setting'."
        ),
    )
    global_other_digest_model = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=_("Specify model name if 'Other' is selected above, e.g. 'grok-3' in xAI"),
        verbose_name=_("Global Other Digest Model"),
    )

    class Meta:
        verbose_name = _("App Setting")
        verbose_name_plural = _("App Settings")

    def __str__(self):
        return "App Settings"

    def save(self, *args, **kwargs):
        """Enforce singleton pattern - only one AppSetting instance allowed"""
        if not self.pk and AppSetting.objects.exists():
            # If creating new instance and one already exists, update the existing one instead
            existing = AppSetting.objects.first()
            self.pk = existing.pk
            self.id = existing.id
        super().save(*args, **kwargs)

    @classmethod
    def get_instance(cls):
        """Get the singleton AppSetting instance if it exists, None otherwise.
        Does NOT auto-create to avoid unintended side effects."""
        try:
            return cls.objects.get(pk=1)
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_or_create_instance(cls):
        """Get or create the singleton AppSetting instance with safe defaults"""
        instance, created = cls.objects.get_or_create(
            pk=1,  # Always use pk=1 for singleton
            defaults={
                "global_summary_model": "none",
                "global_digest_model": "none",
            },
        )
        return instance

    @classmethod
    def get_auth_code(cls):
        instance = cls.objects.first()
        return instance.auth_code if instance else None

    @classmethod
    def get_global_summary_model(cls):
        """Get the effective global summary model, handling 'none' and 'other' selections.
        Returns None if 'none' is selected, indicating AI features should be disabled."""
        instance = cls.objects.first()
        if not instance:
            return None  # No AppSetting configured, disable AI
        if instance.global_summary_model == "none":
            return None  # Explicitly disabled
        if instance.global_summary_model == "other":
            return instance.global_other_summary_model or None
        return instance.global_summary_model

    @classmethod
    def get_global_digest_model(cls):
        """Get the effective global digest model, handling 'none' and 'other' selections.
        Returns None if 'none' is selected, indicating AI features should be disabled."""
        instance = cls.objects.first()
        if not instance:
            return None  # No AppSetting configured, disable AI
        if instance.global_digest_model == "none":
            return None  # Explicitly disabled
        if instance.global_digest_model == "other":
            return instance.global_other_digest_model or None
        return instance.global_digest_model


class OriginalFeed(models.Model):
    url = models.URLField(unique=True, help_text=_("RSS or Atom feed URL"), max_length=2048, verbose_name=_("URL"))
    title = models.CharField(
        max_length=255, blank=True, default="", help_text=_("Display name for this feed"), verbose_name=_("Title")
    )
    max_articles_to_keep = models.PositiveIntegerField(
        default=1000,
        help_text=_("Older articles will be removed when limit is reached"),
        verbose_name=_("Max Articles to Keep"),
    )
    # tag = models.CharField(max_length=255, blank=True, default='', help_text="Optional tag for the original feed")
    tags: "ManyToManyField[Tag, OriginalFeed]" = models.ManyToManyField(
        "Tag", related_name="original_feeds", blank=True, verbose_name=_("Tags")
    )
    valid = models.BooleanField(default=None, blank=True, null=True, editable=False, verbose_name=_("Valid"))

    class Meta:
        verbose_name = _("Original Feed")
        verbose_name_plural = _("Original Feeds")

    def __str__(self):
        return self.title or self.url

    def save(self, *args, **kwargs):
        if not self.title:
            self.title = self.url
        super().save(*args, **kwargs)


class Tag(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name=_("Name"))

    class Meta:
        verbose_name = _("Tag")
        verbose_name_plural = _("Tags")

    def __str__(self):
        return self.name


class ProcessedFeed(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name=_("Name"))  # Ensure subscription name is unique
    last_modified = models.DateTimeField(
        default=None, blank=True, null=True, editable=False, verbose_name=_("Last Modified")
    )
    feeds: "ManyToManyField[OriginalFeed, ProcessedFeed]" = models.ManyToManyField(
        "OriginalFeed",
        related_name="processed_feeds",
        help_text=_("Original feeds to aggregate into this processed feed"),
        verbose_name=_("Original Feeds"),
    )

    # Summarization related fields
    articles_to_summarize_per_interval = models.PositiveIntegerField(
        default=0,
        help_text=_(
            "Number of articles to summarize per update. All articles included in feed, set to 0 to disable summarization"
        ),
        verbose_name=_("Articles to summarize per update"),
    )
    summary_language = models.CharField(
        max_length=20,
        default="English",
        help_text=_("Target language for summarization. Ignored if using custom prompt"),
        verbose_name=_("Summary Language"),
    )
    additional_prompt = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Custom Prompt"),
        help_text=_("Override default summarization prompt. Can be used for translation or custom instructions"),
    )
    translate_title = models.BooleanField(
        default=False,
        verbose_name=_("Article Title Translation"),
        help_text=_("Translate article titles to summary language"),
    )
    model = models.CharField(
        max_length=255,
        default="use_global",
        choices=MODEL_CHOICES,
        verbose_name=_("Summary Model"),
        help_text=_(
            "AI model for summarization. Note: Requires global AI to be enabled in App Settings. "
            "If global AI is disabled (set to 'None'), this setting will have no effect."
        ),
    )
    other_model = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=_("Specify model name if 'Other' is selected above, e.g. 'grok-3' in xAI"),
        verbose_name=_("Other Model"),
    )

    # Digest related fields
    toggle_digest = models.BooleanField(
        default=False, help_text=_("Generate periodic digest of the feed"), verbose_name=_("Enable Digest")
    )
    toggle_entries = models.BooleanField(
        default=True,
        help_text=_("Include individual entries in feed. Disable to only generate digest"),
        verbose_name=_("Include Entries"),
    )
    digest_frequency = models.CharField(
        max_length=20,
        default="daily",
        choices=[("daily", _("Daily")), ("weekly", _("Weekly"))],
        verbose_name=_("Digest Frequency"),
    )
    last_digest = models.DateTimeField(
        default=None,
        blank=True,
        null=True,
        editable=True,
        help_text=_("Last digest generation time. Modify to reset timer or force new digest"),
        verbose_name=_("Last Digest"),
    )
    include_toc = models.BooleanField(default=True, verbose_name=_("Include Table of Contents"))
    include_one_line_summary = models.BooleanField(
        default=True,
        help_text=_("Only works with default summarization (no custom prompt)"),
        verbose_name=_("Include One Line Summary"),
    )
    include_summary = models.BooleanField(default=False, verbose_name=_("Include Full Summary"))
    include_content = models.BooleanField(default=False, verbose_name=_("Include Full Content"))

    # AI-digest related fields
    use_ai_digest = models.BooleanField(default=False, verbose_name=_("Use AI Digest"))
    send_full_article = models.BooleanField(
        default=False,
        help_text=_(
            "Send full article content to AI. Ignored without digest prompt. Default sends only link, title, and summary"
        ),
        verbose_name=_("Send Full Article"),
    )
    digest_model = models.CharField(
        max_length=255,
        default="use_global",
        choices=MODEL_CHOICES,
        verbose_name=_("Digest Model"),
        help_text=_(
            "AI model for digest generation. Note: Requires global AI to be enabled in App Settings. "
            "If global AI is disabled (set to 'None'), this setting will have no effect."
        ),
    )
    other_digest_model = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=_("Specify OpenAI-compatible model if 'Other' is selected above, e.g. 'grok-3' in xAI"),
        verbose_name=_("Other Digest Model"),
    )
    additional_prompt_for_digest = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Digest Prompt"),
        help_text=_("Custom prompt for AI digest generation. Without this, only title, link and summary are included"),
    )

    # Filter related fields
    feed_group_relational_operator = models.CharField(
        max_length=20,
        choices=[("all", _("All")), ("any", _("Any")), ("none", _("None"))],
        default="any",
        help_text=_("Logic between filter groups for feed inclusion: match All/Any/None of the filter groups"),
        verbose_name=_("Logic Between Feed Filter Groups"),
    )
    summary_group_relational_operator = models.CharField(
        max_length=20,
        choices=[("all", _("All")), ("any", _("Any")), ("none", _("None"))],
        default="any",
        help_text=_("Logic between filter groups for summarization: match All/Any/None of the filter groups"),
        verbose_name=_("Logic Between Summary Filter Groups"),
    )
    case_sensitive = models.BooleanField(
        default=False,
        help_text=_("Enable case-sensitive filter matching. Default is case-insensitive"),
        verbose_name=_("Case Sensitive"),
    )

    class Meta:
        verbose_name = _("Processed Feed")
        verbose_name_plural = _("Processed Feeds")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        async_update_feeds_and_digest(self.name)

    def clean(self):
        if not self.toggle_digest and not self.toggle_entries:
            raise ValidationError(_("At least one of 'Enable Digest' or 'Include Entries' must be enabled."))

    def get_effective_summary_model(self):
        """Get the effective summary model, considering global settings as master switch.
        Returns None if global is disabled, indicating AI features should be disabled."""
        # First check if global AI is enabled at all
        global_model = AppSetting.get_global_summary_model()
        if global_model is None:
            # Global AI is disabled - no AI features work regardless of individual settings
            return None

        # Global AI is enabled, now check what model to use
        if self.model == "use_global":
            return global_model
        elif self.model == "other":
            return self.other_model if self.other_model else None
        return self.model

    def get_effective_digest_model(self):
        """Get the effective digest model, considering global settings as master switch.
        Returns None if global is disabled, indicating AI features should be disabled."""
        # First check if global AI is enabled at all
        global_model = AppSetting.get_global_digest_model()
        if global_model is None:
            # Global AI is disabled - no AI features work regardless of individual settings
            return None

        # Global AI is enabled, now check what model to use
        if self.digest_model == "use_global":
            return global_model
        elif self.digest_model == "other":
            return self.other_digest_model if self.other_digest_model else None
        return self.digest_model


@receiver(m2m_changed, sender=ProcessedFeed.feeds.through)
def reset_last_modified(sender, instance, action, **kwargs):
    if action in ["post_add", "post_remove", "post_clear"]:
        ProcessedFeed.objects.filter(pk=instance.pk).update(last_modified=None, last_digest=None)


class FilterGroup(models.Model):
    PROCESSED_FEED_CHOICES = (
        ("feed_filter", _("Feed Filter")),
        ("summary_filter", _("Summary Filter")),
    )
    RELATIONAL_OPERATOR_CHOICES = (
        ("all", _("All")),
        ("any", _("Any")),
        ("none", _("None")),
    )

    processed_feed = models.ForeignKey(
        ProcessedFeed, on_delete=models.CASCADE, related_name="filter_groups", verbose_name=_("Processed Feed")
    )
    usage = models.CharField(
        max_length=15, choices=PROCESSED_FEED_CHOICES, default="feed_filter", verbose_name=_("Usage")
    )
    relational_operator = models.CharField(
        max_length=20, choices=RELATIONAL_OPERATOR_CHOICES, default="any", verbose_name=_("Relational Operator")
    )

    class Meta:
        verbose_name = _("Filter Group")
        verbose_name_plural = _("Filter Groups")

    def __str__(self):
        return f"{self.usage}"


class Filter(models.Model):
    FIELD_CHOICES = (
        ("title", _("Title")),
        ("content", _("Content")),
        ("link", _("Link")),
        ("title_or_content", _("Title or content")),
    )
    MATCH_TYPE_CHOICES = (
        ("contains", _("Contains")),
        ("does_not_contain", _("Does not contain")),
        ("matches_regex", _("Matches regex")),
        ("does_not_match_regex", _("Does not match regex")),
        ("shorter_than", _("Shorter than")),
        ("longer_than", _("Longer than")),
    )
    filter_group = models.ForeignKey(
        FilterGroup, on_delete=models.CASCADE, related_name="filters", verbose_name=_("Filter Group")
    )  # null=True, default=None)
    field = models.CharField(max_length=20, choices=FIELD_CHOICES, verbose_name=_("Field"))
    match_type = models.CharField(max_length=20, choices=MATCH_TYPE_CHOICES, verbose_name=_("Match Type"))
    value = models.TextField(verbose_name=_("Value"))

    class Meta:
        verbose_name = _("Filter")
        verbose_name_plural = _("Filters")

    def __str__(self):
        return f"{self.field} {self.match_type} {self.value[:20]}"

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def clean(self):
        # Validate value based on match_type
        if self.match_type in ["shorter_than", "longer_than"]:
            if not self.value.isdigit():
                raise ValidationError(_("Value must be a positive integer for length comparisons."))
            elif int(self.value) <= 0:
                raise ValidationError(_("Value must be a positive integer greater than zero."))
        elif self.match_type in ["matches_regex", "does_not_match_regex"]:
            try:
                re.compile(self.value)
            except re.error:
                raise ValidationError(_("Invalid regular expression.")) from None


class Article(models.Model):
    original_feed = models.ForeignKey(
        OriginalFeed, on_delete=models.CASCADE, related_name="articles", verbose_name=_("Original Feed")
    )
    title = models.CharField(max_length=255, verbose_name=_("Title"))
    link = models.URLField(verbose_name=_("Link"))
    published_date = models.DateTimeField(verbose_name=_("Published Date"))
    content = models.TextField(blank=True, null=True, verbose_name=_("Content"))
    summary = models.TextField(blank=True, null=True, verbose_name=_("Summary"))
    summary_one_line = models.TextField(blank=True, null=True, verbose_name=_("One Line Summary"))
    summarized = models.BooleanField(default=False, verbose_name=_("Summarized"))
    custom_prompt = models.BooleanField(default=False, verbose_name=_("Custom Prompt Used"))

    # URL should not be unique when different original feeds have the same article
    # The unique check should happen when adding articles to a ProcessedFeed
    class Meta:
        unique_together = ("link", "original_feed")
        verbose_name = _("Article")
        verbose_name_plural = _("Articles")

    def __str__(self):
        return self.title


class Digest(models.Model):
    processed_feed = models.ForeignKey(
        ProcessedFeed, on_delete=models.CASCADE, related_name="digests", verbose_name=_("Processed Feed")
    )
    content = models.TextField(verbose_name=_("Content"))
    start_time = models.DateTimeField(default=None, blank=True, null=True, verbose_name=_("Start Time"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))

    class Meta:
        verbose_name = _("Digest")
        verbose_name_plural = _("Digests")

    def __str__(self):
        return _("Digest for %(feed_name)s from %(created_at)s") % {
            "feed_name": self.processed_feed.name,
            "created_at": self.created_at,
        }
