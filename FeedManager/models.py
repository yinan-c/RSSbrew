from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
import re
from .tasks import async_update_feeds_and_digest

DEFAULT_MODEL = getattr(settings, 'OPENAI_DEFAULT_MODEL', 'gpt-4.1-mini')

MODEL_CHOICES = [
    ('gpt-4.1-mini', 'GPT-4.1 Mini'),
    ('gpt-4.1-nano', 'GPT-4.1 Nano'),
    ('gpt-4.1', 'GPT-4.1'),
    ('gpt-4.5-preview', 'GPT-4.5 Preview'),
    ('gpt-4o-mini', 'GPT-4o Mini'),
    ('gpt-4o', 'GPT-4o'),
    ('gpt-4-turbo', 'GPT-4 Turbo'),
    ('gpt-3.5-turbo', 'GPT-3.5 Turbo'),
    ('other', _('Other (specify below)')),
]

if DEFAULT_MODEL not in [choice[0] for choice in MODEL_CHOICES]:
    MODEL_CHOICES.insert(0, (DEFAULT_MODEL, f"{DEFAULT_MODEL} (Default)"))

class AppSetting(models.Model):
    auth_code = models.CharField(max_length=64, blank=True, null=True, verbose_name=_('Auth Code'))

    class Meta:
        verbose_name = _('App Setting')
        verbose_name_plural = _('App Settings')

    @classmethod
    def get_auth_code(cls):
        instance = cls.objects.first()
        return instance.auth_code if instance else None

class OriginalFeed(models.Model):
    url = models.URLField(unique=True, help_text=_("URL of the Atom or RSS feed"), max_length=2048, verbose_name=_('URL'))
    title = models.CharField(max_length=255, blank=True, default='', help_text=_("Optional title for the original feed"), verbose_name=_('Title'))
    max_articles_to_keep = models.PositiveIntegerField(default=1000, help_text=_("Older articles will be removed when the limit is reached."), verbose_name=_('Max Articles to Keep'))
    #tag = models.CharField(max_length=255, blank=True, default='', help_text="Optional tag for the original feed")
    tags = models.ManyToManyField('Tag', related_name='original_feeds', blank=True, help_text=_("Tags associated with this feed"), verbose_name=_('Tags'))
    valid = models.BooleanField(default=None, blank=True, null=True, editable=False, help_text=_("Whether the feed is valid."), verbose_name=_('Valid'))

    def save(self, *args, **kwargs):
        if not self.title:
            self.title = self.url
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = _('Original Feed')
        verbose_name_plural = _('Original Feeds')

    def __str__(self):
        return self.title or self.url

class Tag(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name=_('Name'))

    class Meta:
        verbose_name = _('Tag')
        verbose_name_plural = _('Tags')

    def __str__(self):
        return self.name

class ProcessedFeed(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name=_('Name')) # Ensure subscription name is unique
    last_modified = models.DateTimeField(default=None, blank=True, null=True, editable=False, verbose_name=_('Last Modified'))
    feeds = models.ManyToManyField('OriginalFeed', related_name='processed_feeds', help_text=_("All selected original feeds will be aggregated into this feed."), verbose_name=_('Original Feeds'))

    # Summarization related fields
    articles_to_summarize_per_interval = models.PositiveIntegerField(default=0, help_text=_("All articles will be included in the feed, but only the set number of articles will be summarized per update, set to 0 to disable summarization."), verbose_name=_("Articles to summarize per update"))
    summary_language = models.CharField(max_length=20, default='English', help_text=_("Language for summarization, will be ignored if summarization is disabled or using custom prompt."), verbose_name=_('Summary Language'))
    additional_prompt = models.TextField(blank=True, default='', verbose_name=_('Custom Prompt'), help_text=_("This prompt will override the default prompt for summarization, you can use it for translation or other detailed instructions."))
    translate_title = models.BooleanField(default=False, verbose_name=_("Article Title Translation"), help_text=_("If this option is true, Article title is translated to summary language."))
    model = models.CharField(
        max_length=255,
        default=DEFAULT_MODEL,
        choices=MODEL_CHOICES,
        verbose_name=_('Model')
    )
    other_model = models.CharField(max_length=255, blank=True, default='', help_text=_("Please specify the model if 'Other' is selected above, e.g. 'gemini-1.5-pro' in OneAPI."), verbose_name=_('Other Model'))

    # Digest related fields
    toggle_digest = models.BooleanField(default=False, help_text=_("Send a digest of the feed regularly."), verbose_name=_('Enable Digest'))
    toggle_entries = models.BooleanField(default=True, help_text=_("Include entries in the feed, disable to only send digest regularly."), verbose_name=_('Include Entries')) 
    digest_frequency = models.CharField(max_length=20, default='daily', choices=[('daily', _('Daily')), ('weekly', _('Weekly'))], help_text=_("Frequency of the digest."), verbose_name=_('Digest Frequency'))
    last_digest = models.DateTimeField(default=None, blank=True, null=True, editable=True, help_text=_("Last time the digest was generated, change if you want to reset the digest timer or force a new digest."), verbose_name=_('Last Digest'))
    include_toc = models.BooleanField(default=True, help_text=_("Include table of contents in digest."), verbose_name=_('Include Table of Contents'))
    include_one_line_summary = models.BooleanField(default=True, help_text=_("Include one line summary in digest, only works for default summarization."), verbose_name=_('Include One Line Summary'))
    include_summary = models.BooleanField(default=False, help_text=_("Include full summary in digest."), verbose_name=_('Include Full Summary'))
    include_content = models.BooleanField(default=False, help_text=_("Include full content in digest."), verbose_name=_('Include Full Content'))

    # AI-digest related fields
    use_ai_digest = models.BooleanField(default=False, help_text=_("Use AI to process digest content."), verbose_name=_('Use AI Digest'))
    send_full_article = models.BooleanField(default=False, help_text=_("(Ignored without prompt) Send full article content for AI digest, by default only link, title, and summary are sent."), verbose_name=_('Send Full Article'))
    digest_model = models.CharField(
        max_length=255,
        default=DEFAULT_MODEL,
        choices=MODEL_CHOICES,
        help_text=_("Model for digest generation."),
        verbose_name=_('Digest Model')
    )
    other_digest_model = models.CharField(max_length=255, blank=True, default='', help_text=_("Please specify the OpenAI-compatible model if 'Other' is selected above, e.g. 'grok-3-beta' in GrokAI or OneAPI."), verbose_name=_('Other Digest Model'))
    additional_prompt_for_digest = models.TextField(blank=True, default='', verbose_name=_('(Optional) Prompt for Digest'), help_text=_("Using AI to generate digest, otherwise only the title, link and summary from the database will be included in the digest."))

    # Filter related fields
    feed_group_relational_operator = models.CharField(max_length=20, choices=[('all', _('All')), ('any', _('Any')), ('none', _('None'))], default='any', help_text=_("The included articles must match All/Any/None of the filters."), verbose_name=_('Feed Filter Logic'))
    summary_group_relational_operator = models.CharField(max_length=20, choices=[('all', _('All')), ('any', _('Any')), ('none', _('None'))], default='any', help_text=_("The included articles must match All/Any/None of the filters for summarization."), verbose_name=_('Summary Filter Logic'))
    case_sensitive = models.BooleanField(default=False, help_text=_("For filter keyword, default to unchecked for ignoring case."), verbose_name=_('Case Sensitive'))
    
    class Meta:
        verbose_name = _('Processed Feed')
        verbose_name_plural = _('Processed Feeds')
    
    def __str__(self):
        return self.name

    def clean(self):
        if not self.toggle_digest and not self.toggle_entries:
            raise ValidationError(_("At least one of 'toggle digest' or 'toggle entries' must be enabled."))

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        async_update_feeds_and_digest(self.name)

@receiver(m2m_changed, sender=ProcessedFeed.feeds.through)
def reset_last_modified(sender, instance, action, **kwargs):
    if action in ["post_add", "post_remove", "post_clear"]:
        ProcessedFeed.objects.filter(pk=instance.pk).update(last_modified=None, last_digest=None)

class FilterGroup(models.Model):
    PROCESSED_FEED_CHOICES = (
        ('feed_filter', _('Feed Filter')),
        ('summary_filter', _('Summary Filter')),
    )
    RELATIONAL_OPERATOR_CHOICES = (
        ('all', _('All')),
        ('any', _('Any')),
        ('none', _('None')),
    )

    processed_feed = models.ForeignKey(ProcessedFeed, on_delete=models.CASCADE, related_name='filter_groups', verbose_name=_('Processed Feed'))
    usage = models.CharField(max_length=15, choices=PROCESSED_FEED_CHOICES, default='feed_filter', verbose_name=_('Usage'))
    relational_operator = models.CharField(max_length=20, choices=RELATIONAL_OPERATOR_CHOICES, default='any', verbose_name=_('Relational Operator'))

    class Meta:
        verbose_name = _('Filter Group')
        verbose_name_plural = _('Filter Groups')

    def __str__(self):
        return f"{self.usage}"

class Filter(models.Model):
    FIELD_CHOICES = (
        ('title', _('Title')),
        ('content', _('Content')),
        ('link', _('Link')),
        ('title_or_content', _('Title or content')),
    )
    MATCH_TYPE_CHOICES = (
        ('contains', _('Contains')),
        ('does_not_contain', _('Does not contain')),
        ('matches_regex', _('Matches regex')),
        ('does_not_match_regex', _('Does not match regex')),
        ('shorter_than', _('Shorter than')),
        ('longer_than', _('Longer than')),
    )
    filter_group = models.ForeignKey(FilterGroup, on_delete=models.CASCADE, related_name='filters', verbose_name=_('Filter Group')) #null=True, default=None)
    field = models.CharField(max_length=20, choices=FIELD_CHOICES, verbose_name=_('Field'))
    match_type = models.CharField(max_length=20, choices=MATCH_TYPE_CHOICES, verbose_name=_('Match Type'))
    value = models.TextField(verbose_name=_('Value'))

    class Meta:
        verbose_name = _('Filter')
        verbose_name_plural = _('Filters')

    def clean(self):
        # Validate value based on match_type
        if self.match_type in ['shorter_than', 'longer_than']:
            if not self.value.isdigit():
                raise ValidationError(_("Value must be a positive integer for length comparisons."))
            elif int(self.value) <= 0:
                raise ValidationError(_("Value must be a positive integer greater than zero."))
        elif self.match_type in ['matches_regex', 'does_not_match_regex']:
            try:
                re.compile(self.value)
            except re.error:
                raise ValidationError(_("Invalid regular expression."))

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

class Article(models.Model):
    original_feed = models.ForeignKey(OriginalFeed, on_delete=models.CASCADE, related_name='articles', verbose_name=_('Original Feed'))
    title = models.CharField(max_length=255, verbose_name=_('Title'))
    link = models.URLField(verbose_name=_('Link'))
    published_date = models.DateTimeField(verbose_name=_('Published Date'))
    content = models.TextField(blank=True, null=True, verbose_name=_('Content'))
    summary = models.TextField(blank=True, null=True, verbose_name=_('Summary'))
    summary_one_line = models.TextField(blank=True, null=True, verbose_name=_('One Line Summary'))
    summarized = models.BooleanField(default=False, verbose_name=_('Summarized'))
    custom_prompt = models.BooleanField(default=False, verbose_name=_('Custom Prompt Used'))
    # URL should not be unique when different original feeds have the same article
    # The unique check should happen when adding articles to a ProcessedFeed
    class Meta:
        unique_together = ('link', 'original_feed')
        verbose_name = _('Article')
        verbose_name_plural = _('Articles')

    def __str__(self):
        return self.title

class Digest(models.Model):
    processed_feed = models.ForeignKey(ProcessedFeed, on_delete=models.CASCADE, related_name='digests', verbose_name=_('Processed Feed'))
    content = models.TextField(verbose_name=_('Content'))
    start_time = models.DateTimeField(default=None, blank=True, null=True, verbose_name=_('Start Time'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))

    class Meta:
        verbose_name = _('Digest')
        verbose_name_plural = _('Digests')

    def __str__(self):
        return f"Digest for {self.processed_feed.name} from {self.created_at}"
