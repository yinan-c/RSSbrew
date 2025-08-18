from django.core.management.base import BaseCommand
from django.utils import translation
from django.utils.translation import gettext as _
from FeedManager.models import ProcessedFeed, OriginalFeed, Filter

class Command(BaseCommand):
    help = 'Test Chinese translations'

    def handle(self, *args, **options):
        # Test English
        with translation.override('en'):
            self.stdout.write("\n=== English ===")
            self.stdout.write(f"Original Feed: {OriginalFeed._meta.verbose_name}")
            self.stdout.write(f"Processed Feed: {ProcessedFeed._meta.verbose_name}")
            self.stdout.write(f"Filter: {Filter._meta.verbose_name}")
            self.stdout.write(f"Model field 'URL': {OriginalFeed._meta.get_field('url').verbose_name}")
            self.stdout.write(f"Help text: {OriginalFeed._meta.get_field('url').help_text}")
            
        # Test Chinese
        with translation.override('zh-hans'):
            self.stdout.write("\n=== 简体中文 ===")
            self.stdout.write(f"Original Feed: {OriginalFeed._meta.verbose_name}")
            self.stdout.write(f"Processed Feed: {ProcessedFeed._meta.verbose_name}")
            self.stdout.write(f"Filter: {Filter._meta.verbose_name}")
            self.stdout.write(f"Model field 'URL': {OriginalFeed._meta.get_field('url').verbose_name}")
            self.stdout.write(f"Help text: {OriginalFeed._meta.get_field('url').help_text}")
            
        self.stdout.write("\n" + self.style.SUCCESS('Translation test completed!'))