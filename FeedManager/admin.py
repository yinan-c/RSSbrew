from django.contrib import admin
from .models import ProcessedFeed, OriginalFeed, Filter, Article, AppSetting
from django.utils.html import format_html
from django.urls import reverse
from .forms import FilterForm, ReadOnlyArticleForm
from django.contrib.auth.models import User, Group

class FilterInline(admin.TabularInline):
    model = Filter
    form = FilterForm
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

class ProcessedFeedAdmin(admin.ModelAdmin):
    inlines = [FilterInline]
    list_display = ('name', 'update_frequency', 'max_articles_to_process_per_interval')
    filter_horizontal = ('feeds',)
    search_fields = ('name', 'feeds__title', 'feeds__url')
    list_filter = ('update_frequency', 'max_articles_to_process_per_interval')

class OriginalFeedAdmin(admin.ModelAdmin):
    inlines = [ArticleInline]
    search_fields = ('title', 'url')
    
admin.site.register(ProcessedFeed, ProcessedFeedAdmin)
admin.site.register(OriginalFeed, OriginalFeedAdmin)

@admin.register(AppSetting)
class AppSettingAdmin(admin.ModelAdmin):
    list_display = ['auth_code']
    fields = ['auth_code']

admin.site.unregister(User)
admin.site.unregister(Group)