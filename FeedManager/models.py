from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.core.exceptions import ValidationError
import re
from .tasks import async_update_feeds_and_digest

class AppSetting(models.Model):
    auth_code = models.CharField(max_length=64, blank=True, null=True)

    @classmethod
    def get_auth_code(cls):
        instance = cls.objects.first()
        return instance.auth_code if instance else None

class OriginalFeed(models.Model):
    url = models.URLField(unique=True, help_text="URL of the Atom or RSS feed", max_length=2048)
    title = models.CharField(max_length=255, blank=True, default='', help_text="Optional title for the original feed")
    max_articles_to_keep = models.PositiveIntegerField(default=1000, help_text="Older articles will be removed when the limit is reached.")
    #tag = models.CharField(max_length=255, blank=True, default='', help_text="Optional tag for the original feed")
    tags = models.ManyToManyField('Tag', related_name='original_feeds', blank=True, help_text="Tags associated with this feed")
    valid = models.BooleanField(default=None, blank=True, null=True, editable=False, help_text="Whether the feed is valid.")

    def save(self, *args, **kwargs):
        if not self.title:
            self.title = self.url
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title or self.url

class Tag(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name

class ProcessedFeed(models.Model):
    name = models.CharField(max_length=255, unique=True) # Ensure subscription name is unique
    last_modified = models.DateTimeField(default=None, blank=True, null=True, editable=False)
    feeds = models.ManyToManyField('OriginalFeed', related_name='processed_feeds', help_text="All selected original feeds will be aggregated into this feed.")

    # Summarization related fields
    articles_to_summarize_per_interval = models.PositiveIntegerField(default=0, help_text="All articles will be included in the feed, but only the set number of articles will be summarized per update, set to 0 to disable summarization.", verbose_name="Articles to summarize per update")
    summary_language = models.CharField(max_length=20, default='English', help_text="Language for summarization, will be ignored if summarization is disabled or using custom prompt.")
    additional_prompt = models.TextField(blank=True, default='', verbose_name='Custom Prompt', help_text="This prompt will override the default prompt for summarization, you can use it for translation or other detailed instructions.")
    translate_title = models.BooleanField(default=False, verbose_name="Article Title Translation", help_text="If this options is true, Article title is translated to summary language.")
    choices = [ 
        ('gpt-3.5-turbo', 'GPT-3.5 Turbo'),
        ('gpt-4-turbo', 'GPT-4 Turbo'),
        ('gpt-4o', 'GPT-4o'),
        ('gpt-4o-mini', 'GPT-4o Mini'),
        ('other', 'Other (specify below)'),
    ]  
    model = models.CharField(max_length=20, default='gpt-3.5-turbo', choices=choices)
    other_model = models.CharField(max_length=255, blank=True, default='', help_text="Please specify the model if 'Other' is selected above, e.g. 'gemini-1.5-pro' in OneAPI.")

    # Digest related fields
    toggle_digest = models.BooleanField(default=False, help_text="Send a digest of the feed regularly.")
    toggle_entries = models.BooleanField(default=True, help_text="Include entries in the feed, disable to only send digest regularly.") 
    digest_frequency = models.CharField(max_length=20, default='daily', choices=[('daily', 'Daily'), ('weekly', 'Weekly')], help_text="Frequency of the digest.")
    last_digest = models.DateTimeField(default=None, blank=True, null=True, editable=True, help_text="Last time the digest was generated, change if you want to reset the digest timer or force a new digest.")
    include_toc = models.BooleanField(default=True, help_text="Include table of contents in digest.")
    include_one_line_summary = models.BooleanField(default=True, help_text="Include one line summary in digest, only works for default summarization.")
    include_summary = models.BooleanField(default=False, help_text="Include full summary in digest.")
    include_content = models.BooleanField(default=False, help_text="Include full content in digest.")

    # AI-digest related fields
    use_ai_digest = models.BooleanField(default=False, help_text="Use AI to process digest content.")
    send_full_article = models.BooleanField(default=False, help_text="(Ignored without prompt) Send full article content for AI digest, by default only link, title, and summary are sent.")
    digest_model = models.CharField(max_length=20, default='gpt-3.5-turbo', choices=choices, help_text="Model for digest generation.")
    other_digest_model = models.CharField(max_length=255, blank=True, default='', help_text="Please specify the model if 'Other' is selected above, e.g. 'gemini-1.5-pro' in OneAPI.")
    additional_prompt_for_digest = models.TextField(blank=True, default='', verbose_name='(Optional) Prompt for Digest', help_text="Using AI to generate digest, otherwise only the title, link and summary from the database will be included in the digest.")

    # Filter related fields
    feed_group_relational_operator = models.CharField(max_length=20, choices=[('all', 'All'), ('any', 'Any'), ('none', 'None')], default='any', help_text="The included articles must match All/Any/None of the filters.")
    summary_group_relational_operator = models.CharField(max_length=20, choices=[('all', 'All'), ('any', 'Any'), ('none', 'None')], default='any', help_text="The included articles must match All/Any/None of the filters for summarization.")
    def __str__(self):
        return self.name

    def clean(self):
        if not self.toggle_digest and not self.toggle_entries:
            raise ValidationError("At least one of 'toggle digest' or 'toggle entries' must be enabled.")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        async_update_feeds_and_digest(self.name)

@receiver(m2m_changed, sender=ProcessedFeed.feeds.through)
def reset_last_modified(sender, instance, action, **kwargs):
    if action in ["post_add", "post_remove", "post_clear"]:
        ProcessedFeed.objects.filter(pk=instance.pk).update(last_modified=None, last_digest=None)

class FilterGroup(models.Model):
    PROCESSED_FEED_CHOICES = (
        ('feed_filter', 'Feed Filter'),
        ('summary_filter', 'Summary Filter'),
    )
    RELATIONAL_OPERATOR_CHOICES = (
        ('all', 'All'),
        ('any', 'Any'),
        ('none', 'None'),
    )

    processed_feed = models.ForeignKey(ProcessedFeed, on_delete=models.CASCADE, related_name='filter_groups')
    usage = models.CharField(max_length=15, choices=PROCESSED_FEED_CHOICES, default='feed_filter')
    relational_operator = models.CharField(max_length=20, choices=RELATIONAL_OPERATOR_CHOICES, default='any')

    def __str__(self):
        return f"{self.usage}"

class Filter(models.Model):
    FIELD_CHOICES = (
        ('title', 'Title'),
        ('content', 'Content'),
        ('link', 'Link'),
        ('title_or_content', 'Title or content'),
    )
    MATCH_TYPE_CHOICES = (
        ('contains', 'Contains'),
        ('does_not_contain', 'Does not contain'),
        ('matches_regex', 'Matches regex'),
        ('does_not_match_regex', 'Does not match regex'),
        ('shorter_than', 'Shorter than'),
        ('longer_than', 'Longer than'),
    )
    filter_group = models.ForeignKey(FilterGroup, on_delete=models.CASCADE, related_name='filters') #null=True, default=None)
    field = models.CharField(max_length=20, choices=FIELD_CHOICES)
    match_type = models.CharField(max_length=20, choices=MATCH_TYPE_CHOICES)
    value = models.TextField()

    def clean(self):
        # Validate value based on match_type
        if self.match_type in ['shorter_than', 'longer_than']:
            if not self.value.isdigit():
                raise ValidationError("Value must be a positive integer for length comparisons.")
            elif int(self.value) <= 0:
                raise ValidationError("Value must be a positive integer greater than zero.")
        elif self.match_type in ['matches_regex', 'does_not_match_regex']:
            try:
                re.compile(self.value)
            except re.error:
                raise ValidationError("Invalid regular expression.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

class Article(models.Model):
    original_feed = models.ForeignKey(OriginalFeed, on_delete=models.CASCADE, related_name='articles')
    title = models.CharField(max_length=255)
    link = models.URLField()
    published_date = models.DateTimeField()
    content = models.TextField(blank=True, null=True)
    summary = models.TextField(blank=True, null=True)
    summary_one_line = models.TextField(blank=True, null=True)
    summarized = models.BooleanField(default=False)
    custom_prompt = models.BooleanField(default=False)
    # URL should not be unique when different original feeds have the same article
    # The unique check should happen when adding articles to a ProcessedFeed
    class Meta:
        unique_together = ('link', 'original_feed')

    def __str__(self):
        return self.title

class Digest(models.Model):
    processed_feed = models.ForeignKey(ProcessedFeed, on_delete=models.CASCADE, related_name='digests')
    content = models.TextField()
    start_time = models.DateTimeField(default=None, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Digest for {self.processed_feed.name} from {self.created_at}"
