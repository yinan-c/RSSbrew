from django.db import models
from django.contrib.auth.models import User
from django.conf import settings

LANGUAGE_CHOICES = (
    ('en', 'English'),
    ('zh', 'Chinese'),
    ('es', 'Spanish'),
    ('fr', 'French'),
    ('de', 'German'),
)

class AppSetting(models.Model):
    auth_code = models.CharField(max_length=64, blank=True, null=True)

    @classmethod
    def get_auth_code(cls):
        instance = cls.objects.first()
        return instance.auth_code if instance else None

class OriginalFeed(models.Model):
    url = models.URLField(unique=True)
    title = models.CharField(max_length=255, blank=True, default='')
    max_articles_to_keep = models.PositiveIntegerField(default=1000)

    def save(self, *args, **kwargs):
        if not self.title:
            self.title = self.url
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title or self.url

class ProcessedFeed(models.Model):
    name = models.CharField(max_length=255)
    feeds = models.ManyToManyField('OriginalFeed', related_name='processed_feeds')
    max_articles_to_process_per_interval = models.PositiveIntegerField(default=5)
    summary_language = models.CharField(max_length=50, choices=LANGUAGE_CHOICES, default='English')
    additional_prompt = models.TextField(blank=True)
    choices = [
        ('gpt-3.5-turbo', 'GPT-3.5 Turbo'),
        ('gpt-4-turbo', 'GPT-4 Turbo'),
        ('gpt-4o', 'GPT-4o'),
    ]  
    model = models.CharField(max_length=20, default='gpt-3.5-turbo', choices=choices)
    filter_relational_operator = models.CharField(max_length=20, default='any', choices=[('all', 'All'), ('any', 'Any'), ('none', 'None')])
    def __str__(self):
        return self.name
        
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
    url = models.URLField(unique=True)
    published_date = models.DateTimeField()
    content = models.TextField(blank=True, null=True)
    summary = models.TextField(blank=True, null=True)
    summarized = models.BooleanField(default=False)

    def __str__(self):
        return self.title
