from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

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

    def save(self, *args, **kwargs):
        if not self.title:
            self.title = self.url
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title or self.url

class ProcessedFeed(models.Model):
    name = models.CharField(max_length=255, unique=True) # Ensure subscription name is unique
    last_modified = models.DateTimeField(default=None, blank=True, null=True, editable=False)
    feeds = models.ManyToManyField('OriginalFeed', related_name='processed_feeds', help_text="All selected original feeds will be aggregated into this feed.")
    articles_to_summarize_per_interval = models.PositiveIntegerField(default=0, help_text="All articles will be included in the feed, but only the set number of articles will be summarized per update, set to 0 to disable summarization.", verbose_name="Articles to summarize per update")
    summary_language = models.CharField(max_length=20, default='English', help_text="Language for summarization, will be ignored if summarization is disabled or using custom prompt.")
    additional_prompt = models.TextField(blank=True, default='', verbose_name='Custom Prompt', help_text="This prompt will override the default prompt for summarization, you can use it for translation or other detailed instructions.")
    choices = [ 
        ('gpt-3.5-turbo', 'GPT-3.5 Turbo'),
        ('gpt-4-turbo', 'GPT-4 Turbo'),
        ('gpt-4o', 'GPT-4o'),
    ]  
#    daily_digest = models.BooleanField(default=False, help_text="Send a daily digest email with the latest articles.")
#    digest_time = models.TimeField(default='08:00', help_text="Time of day to send the daily digest email.")
    model = models.CharField(max_length=20, default='gpt-3.5-turbo', choices=choices)
    filter_relational_operator = models.CharField(max_length=20, default='any', choices=[('all', 'All'), ('any', 'Any'), ('none', 'None')], help_text="The included articles must match All/Any/None of the filters.")
    def __str__(self):
        return self.name

@receiver(m2m_changed, sender=ProcessedFeed.feeds.through)
def reset_last_modified(sender, instance, action, **kwargs):
    if action in ["post_add", "post_remove", "post_clear"]:
        ProcessedFeed.objects.filter(pk=instance.pk).update(last_modified=None)
        
from django.core.exceptions import ValidationError
import re

class Filter(models.Model):
    FIELD_CHOICES = (
        ('title', 'Title'),
        ('content', 'Content'),
        ('link', 'Link'),
    )
    MATCH_TYPE_CHOICES = (
        ('contains', 'Contains'),
        ('does_not_contain', 'Does not contain'),
        ('matches_regex', 'Matches regex'),
        ('does_not_match_regex', 'Does not match regex'),
        ('shorter_than', 'Shorter than'),
        ('longer_than', 'Longer than'),
    )
    USAGE_CHOICES = (
        ('feed_filter', 'Feed Filter'),
        ('summary_filter', 'Summary Filter'),
    )
    processed_feed = models.ForeignKey(ProcessedFeed, on_delete=models.CASCADE, related_name='filters')
    field = models.CharField(max_length=15, choices=FIELD_CHOICES)
    match_type = models.CharField(max_length=20, choices=MATCH_TYPE_CHOICES)
    value = models.TextField()
    usage = models.CharField(max_length=15, choices=USAGE_CHOICES, default='feed_filter')

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
    url = models.URLField()
    published_date = models.DateTimeField()
    content = models.TextField(blank=True, null=True)
    summary = models.TextField(blank=True, null=True)
    summary_one_line = models.TextField(blank=True, null=True)
    summarized = models.BooleanField(default=False)
    custom_prompt = models.BooleanField(default=False)
    # URL should not be unique when different original feeds have the same article
    # The unique check should happen when adding articles to a ProcessedFeed
    class Meta:
        unique_together = ('url', 'original_feed')

    def __str__(self):
        return self.title
