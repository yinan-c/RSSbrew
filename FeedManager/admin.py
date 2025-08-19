from django.contrib import admin
from .models import ProcessedFeed, OriginalFeed, Filter, Article, AppSetting, Digest, FilterGroup, Tag
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count
from .forms import FilterForm, ReadOnlyArticleForm, ProcessedFeedAdminForm
from django.contrib.auth.models import User, Group
from django.core.management import call_command
from huey.contrib.djhuey import task
from nested_admin.nested import NestedModelAdmin, NestedTabularInline
from .tasks import async_update_feeds_and_digest, clean_old_articles
from django.utils.translation import gettext_lazy as _
from django.http import HttpResponse
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
from datetime import datetime
import pytz
from django.conf import settings

def update_selected_feeds(modeladmin, request, queryset):
    for feed in queryset:
        async_update_feeds_and_digest(feed.name)
        # If you select a feed to update, you are forcely generating a digest for it
        modeladmin.message_user(request, f"Feed update tasks have been queued for feed: {feed.name}")

def clean_selected_feeds_articles(modeladmin, request, queryset):
    for feed in queryset:
        clean_old_articles(feed.id)
        modeladmin.message_user(request, f"Cleaned old articles from feed: {feed.title}")

clean_selected_feeds_articles.short_description = _("Clean old articles for selected feeds")
update_selected_feeds.short_description = _("Update selected feeds")

def export_original_feeds_as_opml(modeladmin, request, queryset):
    """Export selected original feeds as OPML"""
    # Create OPML structure
    opml = Element('opml')
    opml.set('version', '2.0')
    
    # Create head section
    head = SubElement(opml, 'head')
    title = SubElement(head, 'title')
    title.text = 'RSSBrew Original Feeds Export'
    date_created = SubElement(head, 'dateCreated')
    tz = pytz.timezone(getattr(settings, 'TIME_ZONE', 'UTC'))
    date_created.text = datetime.now(tz).strftime('%a, %d %b %Y %H:%M:%S %z')
    
    # Create body section
    body = SubElement(opml, 'body')
    
    # Add each selected feed as an outline
    for feed in queryset:
        outline = SubElement(body, 'outline')
        outline.set('text', feed.title or feed.url)
        outline.set('title', feed.title or feed.url)
        outline.set('type', 'rss')
        outline.set('xmlUrl', feed.url)
        outline.set('htmlUrl', feed.url)  # Using feed URL as HTML URL since we don't track website URL
        
        # Add tags as categories if present
        tags = feed.tags.all()
        if tags:
            categories = ', '.join([tag.name for tag in tags])
            outline.set('category', categories)
    
    # Convert to pretty XML string
    xml_string = minidom.parseString(tostring(opml, encoding='unicode')).toprettyxml(indent='  ')
    
    # Create HTTP response with OPML content
    response = HttpResponse(xml_string, content_type='text/xml; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="rssbrew_original_feeds_{datetime.now().strftime("%Y%m%d_%H%M%S")}.opml"'
    
    return response

export_original_feeds_as_opml.short_description = _("Export selected feeds as OPML")

def export_processed_feeds_as_opml(modeladmin, request, queryset):
    """Export selected processed feeds as OPML with their original feeds"""
    # Create OPML structure
    opml = Element('opml')
    opml.set('version', '2.0')
    
    # Create head section
    head = SubElement(opml, 'head')
    title = SubElement(head, 'title')
    title.text = 'RSSBrew Processed Feeds Export'
    date_created = SubElement(head, 'dateCreated')
    tz = pytz.timezone(getattr(settings, 'TIME_ZONE', 'UTC'))
    date_created.text = datetime.now(tz).strftime('%a, %d %b %Y %H:%M:%S %z')
    
    # Create body section
    body = SubElement(opml, 'body')
    
    # Add each processed feed as a folder with its original feeds
    for processed_feed in queryset:
        # Create folder for processed feed
        folder = SubElement(body, 'outline')
        folder.set('text', processed_feed.name)
        folder.set('title', processed_feed.name)
        
        # Add the processed feed URL itself
        processed_outline = SubElement(folder, 'outline')
        processed_outline.set('text', f'{processed_feed.name} (Processed Feed)')
        processed_outline.set('title', f'{processed_feed.name} (Processed Feed)')
        processed_outline.set('type', 'rss')
        
        # Generate the processed feed URL
        processed_url = request.build_absolute_uri(reverse('processed_feed_by_name', args=[processed_feed.name]))
        auth_code = AppSetting.get_auth_code()
        if auth_code:
            processed_url += f'?key={auth_code}'
        processed_outline.set('xmlUrl', processed_url)
        processed_outline.set('htmlUrl', processed_url)
        
        # Add all original feeds in this processed feed
        for original_feed in processed_feed.feeds.all():
            outline = SubElement(folder, 'outline')
            outline.set('text', original_feed.title or original_feed.url)
            outline.set('title', original_feed.title or original_feed.url)
            outline.set('type', 'rss')
            outline.set('xmlUrl', original_feed.url)
            outline.set('htmlUrl', original_feed.url)
            
            # Add tags as categories if present
            tags = original_feed.tags.all()
            if tags:
                categories = ', '.join([tag.name for tag in tags])
                outline.set('category', categories)
    
    # Convert to pretty XML string
    xml_string = minidom.parseString(tostring(opml, encoding='unicode')).toprettyxml(indent='  ')
    
    # Create HTTP response with OPML content
    response = HttpResponse(xml_string, content_type='text/xml; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="rssbrew_processed_feeds_{datetime.now().strftime("%Y%m%d_%H%M%S")}.opml"'
    
    return response

export_processed_feeds_as_opml.short_description = _("Export selected feeds as OPML")

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
    readonly_fields = [field.name for field in Article._meta.fields if field.name != 'content']

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

class HasAnyOriginalFeedListFilter(admin.SimpleListFilter):
    title = _('Has any original feed')
    parameter_name = 'has_any_original_feed'

    def lookups(self, request, model_admin):
        return (
            ('yes', _('Yes')),
            ('no', _('No')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.exclude(feeds=None)
        if self.value() == 'no':
            return queryset.filter(feeds=None)

class ProcessedFeedAdmin(NestedModelAdmin):
    form = ProcessedFeedAdminForm
    inlines = [FilterGroupInline]
    # rename articles_to_summarize_per_interval to Summarize per Update in list display
    def summarize_per_update(self, obj):
        return obj.articles_to_summarize_per_interval
    summarize_per_update.short_description = _('Summarize per Update')

    def toggle_digest_and_update(self, obj):
        # An emoji description to show if the digest/entries are enabled
        if obj.toggle_digest and obj.toggle_entries:
            return '✅/✅'
        elif obj.toggle_digest and not obj.toggle_entries:
            return '✅/❌'
        elif not obj.toggle_digest and obj.toggle_entries:
            return '❌/✅'
        else:
            return '❌/❌'
    toggle_digest_and_update.short_description = _('Digest/Entries')

    list_display = ('name', 'summarize_per_update', 'subscription_link', 'original_feed_count', 'toggle_digest_and_update')
#    filter_horizontal = ('feeds',)
    search_fields = ('name', 'feeds__title', 'feeds__url')
    list_filter = ('articles_to_summarize_per_interval', 'summary_language', 'model', HasAnyOriginalFeedListFilter, 'toggle_digest', 'toggle_entries', 'digest_frequency', 'use_ai_digest', 'digest_model')
    actions = [update_selected_feeds, export_processed_feeds_as_opml]
    autocomplete_fields = ['feeds']

    def get_queryset(self, request):
        # Annotate each ProcessedFeed object with the count of related OriginalFeeds
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(_original_feed_count=Count('feeds'))
        return queryset

    def original_feed_count(self, obj):
        # Use the annotated count of related OriginalFeeds
        return obj._original_feed_count
    original_feed_count.admin_order_field = '_original_feed_count'  # Allows column to be sortable
    original_feed_count.short_description = _('Original Feeds')

    fieldsets = (
        (None, {
            'fields': ('name', 'feeds', 'feed_group_relational_operator', 'case_sensitive'),
        }),
        (_('Summarization Options'), {
            'fields': ('articles_to_summarize_per_interval', 'summary_language', 'translate_title', 'model', 'other_model', 'summary_group_relational_operator', 'additional_prompt'),
        }),
        (_('Digest Options'), {
            'fields': ('toggle_entries', 'toggle_digest', 'digest_frequency',  'last_digest'),#, 'include_one_line_summary', 'include_summary', 'include_content',  'use_ai_digest', 'digest_model', 'additional_prompt_for_digest','send_full_article'),
        }),
        (_('What to include in digest'), {
            'fields': ('include_toc', 'include_one_line_summary', 'include_summary', 'include_content', 'use_ai_digest', 'digest_model', 'other_digest_model', 'additional_prompt_for_digest', 'send_full_article'),
        }),
    )

    def subscription_link(self, obj):
        url = reverse('processed_feed_by_name', args=[obj.name])
        auth_code = AppSetting.get_auth_code()  # Get the universal auth code
        if not auth_code:
            return format_html('<a href="{}">Subscribe</a>', url)
        return format_html('<a href="{}?key={}">Subscribe</a>', url, auth_code)
    
    subscription_link.short_description = _("Subscribe Link")

    # Including JavaScript for dynamic form behavior
    class Media:
        js = ('js/admin/toggle_digest_fields.js', 'js/admin/toggle_ai_digest_fields.js')

class IncludedInProcessedFeedListFilter(admin.SimpleListFilter):
    title = _('Included in processed feeds')
    parameter_name = 'included_in_processed_feed'

    def lookups(self, request, model_admin):
        return (
            ('yes', _('Yes')),
            ('no', _('No')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(processed_feeds__isnull=False).distinct()
        if self.value() == 'no':
            return queryset.filter(processed_feeds__isnull=True)

class OriginalFeedAdmin(admin.ModelAdmin):
    inlines = [ArticleInline]
    list_display = ('title', 'valid', 'url', 'processed_feeds_count')
    search_fields = ('title', 'url') 

    def get_queryset(self, request):
        # Annotate each OriginalFeed object with the count of related ProcessedFeeds
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(_processed_feeds_count=Count('processed_feeds'))
        return queryset

    def processed_feeds_count(self, obj):
        # Use the annotated count of related ProcessedFeeds
        return obj._processed_feeds_count
    processed_feeds_count.admin_order_field = '_processed_feeds_count'  # Allows column to be sortable
    processed_feeds_count.short_description = _('Processed Feeds')

    # Filter if the original feed is included in the processed feed
    list_filter = ('valid', 'processed_feeds__name', IncludedInProcessedFeedListFilter, 'tags')
    actions = [clean_selected_feeds_articles, export_original_feeds_as_opml]
    autocomplete_fields = ['tags']

admin.site.register(ProcessedFeed, ProcessedFeedAdmin)
admin.site.register(OriginalFeed, OriginalFeedAdmin)

@admin.register(AppSetting)
class AppSettingAdmin(admin.ModelAdmin):
    list_display = ['auth_code']
    fields = ['auth_code']

admin.site.unregister(User)
admin.site.unregister(Group)

class OriginalFeedInline(admin.TabularInline):
    model = OriginalFeed.tags.through
    extra = 0


class HasAnyOriginalFeedListFilter_Tag(admin.SimpleListFilter):
    title = _('Has any original feed')
    parameter_name = 'has_any_original_feed'

    def lookups(self, request, model_admin):
        return (
            ('yes', _('Yes')),
            ('no', _('No')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.exclude(original_feeds=None)
        if self.value() == 'no':
            return queryset.filter(original_feeds=None)

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        # Annotate each Tag object with the count of related OriginalFeeds
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(_original_feed_count=Count('original_feeds'))
        return queryset
    
    def original_feed_count(self, obj):
        # Use the annotated count of related OriginalFeeds
        return obj._original_feed_count
    original_feed_count.admin_order_field = '_original_feed_count'
    list_display = ['name', 'original_feed_count']
    list_filter = [HasAnyOriginalFeedListFilter_Tag]
    inlines = [OriginalFeedInline]
    search_fields = ['name']

@admin.register(Digest)
class DigestAdmin(admin.ModelAdmin):
    list_display = ['processed_feed', 'created_at', 'start_time']
    search_fields = ['processed_feed__name']