from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

import feedparser

from .models import AppSetting, Article, Filter, FilterGroup, OriginalFeed, ProcessedFeed, Tag
from .utils import match_content, passes_filters


class TestContentFilter(TestCase):
    @patch("FeedManager.models.async_update_feeds_and_digest")
    def setUp(self, mock_async_update):
        """Set up test data"""
        # Create a test user
        self.user = User.objects.create_user(username="testuser", password="testpass")

        # Create an original feed
        self.original_feed = OriginalFeed.objects.create(
            url="https://lorem-rss.herokuapp.com/feed", title="Test Feed", max_articles_to_keep=100
        )

        # Create a processed feed
        self.processed_feed = ProcessedFeed.objects.create(
            name="test_processed_feed",
            feed_group_relational_operator="any",
            summary_group_relational_operator="any",
            case_sensitive=False,
        )
        self.processed_feed.feeds.add(self.original_feed)

    def test_content_filter_with_article_object(self):
        """Test that content filters work correctly with Article objects from database"""

        # Create an article with Lorem in content
        article = Article.objects.create(
            original_feed=self.original_feed,
            title="Test Article",
            link="https://example.com/test",
            published_date=timezone.now(),
            content="Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
        )

        # Create a filter group for feed filtering
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed, usage="feed_filter", relational_operator="any"
        )

        # Create a content filter for "Lorem"
        Filter.objects.create(filter_group=filter_group, field="content", match_type="contains", value="Lorem")

        # Test that the article passes the filter
        result = passes_filters(article, self.processed_feed, "feed_filter")
        self.assertTrue(result, "Article with 'Lorem' in content should pass the filter")

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def test_content_filter_case_insensitive(self, mock_async_update):
        """Test case-insensitive content filtering"""

        # Create an article with lowercase 'lorem' in content
        article = Article.objects.create(
            original_feed=self.original_feed,
            title="Test Article 2",
            link="https://example.com/test2",
            published_date=timezone.now(),
            content="lorem ipsum dolor sit amet, consectetur adipiscing elit.",
        )

        # Create a filter group
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed, usage="feed_filter", relational_operator="any"
        )

        # Create a content filter for "Lorem" (uppercase)
        Filter.objects.create(filter_group=filter_group, field="content", match_type="contains", value="Lorem")

        # Test with case-insensitive (default)
        result = passes_filters(article, self.processed_feed, "feed_filter")
        self.assertTrue(result, "Article with 'lorem' should pass case-insensitive filter for 'Lorem'")

        # Test with case-sensitive
        self.processed_feed.case_sensitive = True
        self.processed_feed.save()
        result = passes_filters(article, self.processed_feed, "feed_filter")
        self.assertFalse(result, "Article with 'lorem' should NOT pass case-sensitive filter for 'Lorem'")

    def test_content_filter_does_not_contain(self):
        """Test 'does not contain' filter type"""

        # Create two articles
        article_with_lorem = Article.objects.create(
            original_feed=self.original_feed,
            title="Article With Lorem",
            link="https://example.com/with-lorem",
            published_date=timezone.now(),
            content="Lorem ipsum dolor sit amet.",
        )

        article_without_lorem = Article.objects.create(
            original_feed=self.original_feed,
            title="Article Without Lorem",
            link="https://example.com/without-lorem",
            published_date=timezone.now(),
            content="This is just plain text without the keyword.",
        )

        # Create a filter group
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed, usage="feed_filter", relational_operator="any"
        )

        # Create a "does not contain" filter for "Lorem"
        Filter.objects.create(filter_group=filter_group, field="content", match_type="does_not_contain", value="Lorem")

        # Test both articles
        result_with = passes_filters(article_with_lorem, self.processed_feed, "feed_filter")
        self.assertFalse(result_with, "Article with 'Lorem' should NOT pass 'does_not_contain' filter")

        result_without = passes_filters(article_without_lorem, self.processed_feed, "feed_filter")
        self.assertTrue(result_without, "Article without 'Lorem' should pass 'does_not_contain' filter")

    def test_title_or_content_filter(self):
        """Test filters that check both title and content"""

        # Create articles with keyword in different places
        article_title_only = Article.objects.create(
            original_feed=self.original_feed,
            title="Lorem in Title",
            link="https://example.com/title-only",
            published_date=timezone.now(),
            content="This content does not have the keyword.",
        )

        article_content_only = Article.objects.create(
            original_feed=self.original_feed,
            title="Regular Title",
            link="https://example.com/content-only",
            published_date=timezone.now(),
            content="Lorem ipsum dolor sit amet.",
        )

        article_neither = Article.objects.create(
            original_feed=self.original_feed,
            title="Regular Title",
            link="https://example.com/neither",
            published_date=timezone.now(),
            content="Regular content without the keyword.",
        )

        # Create a filter group
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed, usage="feed_filter", relational_operator="any"
        )

        # Create a title_or_content filter for "Lorem"
        Filter.objects.create(filter_group=filter_group, field="title_or_content", match_type="contains", value="Lorem")

        # Test all three articles
        self.assertTrue(
            passes_filters(article_title_only, self.processed_feed, "feed_filter"),
            "Article with 'Lorem' in title should pass title_or_content filter",
        )
        self.assertTrue(
            passes_filters(article_content_only, self.processed_feed, "feed_filter"),
            "Article with 'Lorem' in content should pass title_or_content filter",
        )
        self.assertFalse(
            passes_filters(article_neither, self.processed_feed, "feed_filter"),
            "Article without 'Lorem' anywhere should NOT pass title_or_content filter",
        )

    def test_empty_content_handling(self):
        """Test that articles with empty content are handled correctly"""

        # Create an article with no content
        article_no_content = Article.objects.create(
            original_feed=self.original_feed,
            title="Article With No Content",
            link="https://example.com/no-content",
            published_date=timezone.now(),
            content="",  # Empty content
        )

        # Create a filter group
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed, usage="feed_filter", relational_operator="any"
        )

        # Create a content filter for any keyword
        Filter.objects.create(filter_group=filter_group, field="content", match_type="contains", value="Lorem")

        # Article with empty content should not pass a "contains" filter
        result = passes_filters(article_no_content, self.processed_feed, "feed_filter")
        self.assertFalse(result, "Article with empty content should not pass 'contains' filter")

    def test_match_content_direct(self):
        """Test the match_content function directly with Article objects"""

        # Create an article
        article = Article.objects.create(
            original_feed=self.original_feed,
            title="Test Direct Match",
            link="https://example.com/direct",
            published_date=timezone.now(),
            content="Lorem ipsum dolor sit amet.",
        )

        # Create a filter group (needed for filter)
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed, usage="feed_filter", relational_operator="any"
        )

        # Create a filter
        content_filter = Filter.objects.create(
            filter_group=filter_group, field="content", match_type="contains", value="Lorem"
        )

        # Test match_content directly
        result = match_content(article, content_filter, case_sensitive=False)
        self.assertTrue(result, "match_content should return True for Article with matching content")


class TestFeedparserContentFilter(TestCase):
    """Test content filtering with actual feedparser entries (not database objects)"""

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def setUp(self, mock_async_update):
        """Set up test data"""
        # Create an original feed
        self.original_feed = OriginalFeed.objects.create(
            url="https://lorem-rss.herokuapp.com/feed?unit=second&interval=30",
            title="Lorem RSS Test Feed",
            max_articles_to_keep=100,
        )

        # Create a processed feed
        self.processed_feed = ProcessedFeed.objects.create(
            name="lorem_test_feed",
            feed_group_relational_operator="any",
            summary_group_relational_operator="any",
            case_sensitive=False,
        )
        self.processed_feed.feeds.add(self.original_feed)

        # Sample RSS content from the Lorem RSS feed
        self.rss_content = """<?xml version="1.0" encoding="UTF-8"?><rss xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:atom="http://www.w3.org/2005/Atom" version="2.0"><channel><title><![CDATA[Lorem ipsum feed for an interval of 30 seconds with 10 item(s)]]></title><description><![CDATA[This is a constantly updating lorem ipsum feed]]></description><link>http://example.com/</link><generator>RSS for Node</generator><lastBuildDate>Tue, 19 Aug 2025 00:15:03 GMT</lastBuildDate><pubDate>Tue, 19 Aug 2025 00:15:00 GMT</pubDate><copyright><![CDATA[Michael Bertolacci, licensed under a Creative Commons Attribution 3.0 Unported License.]]></copyright><ttl>1</ttl><item><title><![CDATA[Lorem ipsum 2025-08-19T00:15:00Z]]></title><description><![CDATA[Id voluptate sunt in adipisicing occaecat amet mollit fugiat non sunt magna.]]></description><link>http://example.com/test/1755562500</link><guid isPermaLink="true">http://example.com/test/1755562500</guid><dc:creator><![CDATA[John Smith]]></dc:creator><pubDate>Tue, 19 Aug 2025 00:15:00 GMT</pubDate></item><item><title><![CDATA[Lorem ipsum 2025-08-19T00:14:30Z]]></title><description><![CDATA[Dolor aliqua ipsum non labore.]]></description><link>http://example.com/test/1755562470</link><guid isPermaLink="true">http://example.com/test/1755562470</guid><dc:creator><![CDATA[John Smith]]></dc:creator><pubDate>Tue, 19 Aug 2025 00:14:30 GMT</pubDate></item><item><title><![CDATA[Lorem ipsum 2025-08-19T00:14:00Z]]></title><description><![CDATA[Velit fugiat in irure ut adipisicing officia incididunt aute sunt.]]></description><link>http://example.com/test/1755562440</link><guid isPermaLink="true">http://example.com/test/1755562440</guid><dc:creator><![CDATA[John Smith]]></dc:creator><pubDate>Tue, 19 Aug 2025 00:14:00 GMT</pubDate></item></channel></rss>"""

    def test_feedparser_entry_content_filter(self):
        """Test that content filters work with feedparser entries"""

        # Parse the RSS feed
        feed = feedparser.parse(self.rss_content)

        # Create a filter group for feed filtering
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed, usage="feed_filter", relational_operator="any"
        )

        # Create a content filter for "Lorem" (appears in title)
        Filter.objects.create(filter_group=filter_group, field="title", match_type="contains", value="Lorem")

        # Test that entries with "Lorem" in title pass the filter
        for entry in feed.entries:
            result = passes_filters(entry, self.processed_feed, "feed_filter")
            self.assertTrue(result, f"Entry with title '{entry.title}' should pass filter for 'Lorem'")

    def test_feedparser_description_filter(self):
        """Test filtering on description/content field with feedparser entries"""

        # Parse the RSS feed
        feed = feedparser.parse(self.rss_content)

        # Create a filter group
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed, usage="feed_filter", relational_operator="any"
        )

        # Create a content filter for "ipsum" (appears in some descriptions)
        Filter.objects.create(filter_group=filter_group, field="content", match_type="contains", value="ipsum")

        # Check each entry
        expected_results = [
            False,  # "Id voluptate sunt..." - no 'ipsum'
            True,  # "Dolor aliqua ipsum..." - has 'ipsum'
            False,  # "Velit fugiat in..." - no 'ipsum'
        ]

        for i, entry in enumerate(feed.entries[:3]):
            result = passes_filters(entry, self.processed_feed, "feed_filter")
            self.assertEqual(
                result,
                expected_results[i],
                f"Entry {i} with description '{entry.description}' should {'pass' if expected_results[i] else 'not pass'} filter for 'ipsum'",
            )

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def test_feedparser_case_sensitive_filter(self, mock_async_update):
        """Test case-sensitive filtering with feedparser entries"""

        # Parse the RSS feed
        feed = feedparser.parse(self.rss_content)

        # Create a filter group
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed, usage="feed_filter", relational_operator="any"
        )

        # Create a filter for "lorem" (lowercase)
        Filter.objects.create(
            filter_group=filter_group,
            field="title",
            match_type="contains",
            value="lorem",  # lowercase
        )

        # With case-insensitive (default), should match "Lorem" in titles
        for entry in feed.entries:
            result = passes_filters(entry, self.processed_feed, "feed_filter")
            self.assertTrue(
                result, f"Case-insensitive: Entry with title '{entry.title}' should pass filter for 'lorem'"
            )

        # Enable case-sensitive
        self.processed_feed.case_sensitive = True
        self.processed_feed.save()

        # Now it should NOT match because titles have "Lorem" (capital L)
        for entry in feed.entries:
            result = passes_filters(entry, self.processed_feed, "feed_filter")
            self.assertFalse(
                result,
                f"Case-sensitive: Entry with title '{entry.title}' should NOT pass filter for 'lorem' (lowercase)",
            )

    def test_feedparser_title_or_content_filter(self):
        """Test title_or_content filtering with feedparser entries"""

        # Parse the RSS feed
        feed = feedparser.parse(self.rss_content)

        # Create a filter group
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed, usage="feed_filter", relational_operator="any"
        )

        # Create a title_or_content filter for "adipisicing"
        # This word appears in some descriptions but not in titles
        Filter.objects.create(
            filter_group=filter_group, field="title_or_content", match_type="contains", value="adipisicing"
        )

        # Check entries
        # First entry has "adipisicing" in description
        # Second entry doesn't have it
        # Third entry has "adipisicing" in description
        expected_results = [
            True,  # "Id voluptate sunt in adipisicing..."
            False,  # "Dolor aliqua ipsum non labore."
            True,  # "Velit fugiat in irure ut adipisicing..."
        ]

        for i, entry in enumerate(feed.entries[:3]):
            result = passes_filters(entry, self.processed_feed, "feed_filter")
            self.assertEqual(
                result,
                expected_results[i],
                f"Entry {i} should {'pass' if expected_results[i] else 'not pass'} filter for 'adipisicing'",
            )

    def test_feedparser_does_not_contain_filter(self):
        """Test 'does not contain' filter with feedparser entries"""

        # Parse the RSS feed
        feed = feedparser.parse(self.rss_content)

        # Create a filter group
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed, usage="feed_filter", relational_operator="any"
        )

        # Create a "does not contain" filter for "ipsum"
        Filter.objects.create(filter_group=filter_group, field="content", match_type="does_not_contain", value="ipsum")

        # Check entries - opposite of the contains test
        expected_results = [
            True,  # "Id voluptate sunt..." - no 'ipsum'
            False,  # "Dolor aliqua ipsum..." - has 'ipsum'
            True,  # "Velit fugiat in..." - no 'ipsum'
        ]

        for i, entry in enumerate(feed.entries[:3]):
            result = passes_filters(entry, self.processed_feed, "feed_filter")
            self.assertEqual(
                result,
                expected_results[i],
                f"Entry {i} should {'pass' if expected_results[i] else 'not pass'} 'does_not_contain' filter for 'ipsum'",
            )

    def test_html_comments_filter_bug(self):
        """Test that HTML comments don't cause false positive matches in filters"""

        # Mock feedparser entry with HTML comments containing filter keywords
        class MockHtmlEntry:
            def __init__(self):
                self.title = "Lorem Ipsum Article"
                self.link = "https://example.com/lorem-ipsum"
                # HTML content with comments that contain potential filter keywords
                self.content = [
                    {
                        "type": "html",
                        "value": "&lt;!-- TEST_OFF --&gt;&lt;div class=&quot;content&quot;&gt;&lt;p&gt;Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.&lt;/p&gt;&lt;/div&gt;&lt;!-- TEST_ON --&gt;",
                    }
                ]

        entry = MockHtmlEntry()

        # Create filter group with test keywords that appear in HTML comments
        test_filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed, usage="feed_filter", relational_operator="any"
        )

        # Create filters for keywords that could appear in HTML comments/markup
        test_keywords = ["test", "off", "on", "div", "content"]
        for keyword in test_keywords:
            Filter.objects.create(
                filter_group=test_filter_group, field="title_or_content", match_type="contains", value=keyword
            )

        # Import clean_html to analyze the difference
        from .utils import clean_html

        # Build content strings for comparison
        raw_content = entry.title + " " + entry.content[0]["value"]
        cleaned_content = entry.title + " " + clean_html(entry.content[0]["value"])

        # Check if problematic keywords exist in raw vs cleaned content
        raw_has_keywords = any(keyword in raw_content.lower() for keyword in ["off", "test", "div"])
        cleaned_has_keywords = any(keyword in cleaned_content.lower() for keyword in ["off", "test", "div"])

        # Test the filter result
        result = passes_filters(entry, self.processed_feed, "feed_filter")

        # Verify the fix: raw content should have HTML keywords but cleaned shouldn't
        self.assertTrue(raw_has_keywords, "Raw HTML content should contain markup keywords")
        self.assertFalse(cleaned_has_keywords, "Cleaned content should not contain HTML markup keywords")

        # The entry should NOT be included since it only matches HTML markup, not actual content
        self.assertFalse(result, "Entry should NOT pass filters when keywords only exist in HTML markup")


class TestGlobalModelSettings(TestCase):
    """Test global AI model settings and their interaction with individual feed settings"""

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def setUp(self, mock_async_update):
        """Set up test data for model settings tests"""
        # Create an original feed
        self.original_feed = OriginalFeed.objects.create(
            url="https://example.com/feed", title="Test Feed", max_articles_to_keep=100
        )

        # Create a processed feed with default "use_global" setting
        self.processed_feed = ProcessedFeed.objects.create(
            name="test_feed",
            model="use_global",  # Default to use global setting
            digest_model="use_global",  # Default to use global setting
        )
        self.processed_feed.feeds.add(self.original_feed)

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def test_global_none_disables_all_ai(self, mock_async_update):
        """Test that global 'none' setting disables all AI features regardless of individual settings"""
        # Create AppSetting with 'none' for both models
        AppSetting.objects.create(
            global_summary_model="none",
            global_digest_model="none",
        )

        # Test 1: Feed using "use_global" should return None
        self.assertIsNone(self.processed_feed.get_effective_summary_model())
        self.assertIsNone(self.processed_feed.get_effective_digest_model())

        # Test 2: Even if feed has specific model, should still return None (master switch off)
        self.processed_feed.model = "gpt-5-nano"
        self.processed_feed.digest_model = "gpt-5-mini"
        self.processed_feed.save()

        self.assertIsNone(self.processed_feed.get_effective_summary_model())
        self.assertIsNone(self.processed_feed.get_effective_digest_model())

    def test_global_model_with_use_global_feed(self):
        """Test that feeds with 'use_global' inherit the global model setting"""
        # Create AppSetting with specific models
        AppSetting.objects.create(
            global_summary_model="gpt-5-nano",
            global_digest_model="gpt-5-mini",
        )

        # Feed using "use_global" should return the global models
        self.assertEqual(self.processed_feed.get_effective_summary_model(), "gpt-5-nano")
        self.assertEqual(self.processed_feed.get_effective_digest_model(), "gpt-5-mini")

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def test_global_model_with_individual_feed_settings(self, mock_async_update):
        """Test that individual feed settings work when global AI is enabled"""
        # Create AppSetting with models (AI enabled)
        AppSetting.objects.create(
            global_summary_model="gpt-5-nano",
            global_digest_model="gpt-5-mini",
        )

        # Set individual models for the feed
        self.processed_feed.model = "gpt-4o"
        self.processed_feed.digest_model = "gpt-4o-mini"
        self.processed_feed.save()

        # Feed should use its own models, not the global ones
        self.assertEqual(self.processed_feed.get_effective_summary_model(), "gpt-4o")
        self.assertEqual(self.processed_feed.get_effective_digest_model(), "gpt-4o-mini")

    def test_global_other_model_selection(self):
        """Test that 'other' selection in global settings works correctly"""
        # Create AppSetting with 'other' selection
        AppSetting.objects.create(
            global_summary_model="other",
            global_other_summary_model="claude-3-opus",
            global_digest_model="other",
            global_other_digest_model="claude-3-sonnet",
        )

        # Feed using "use_global" should return the custom 'other' models
        self.assertEqual(self.processed_feed.get_effective_summary_model(), "claude-3-opus")
        self.assertEqual(self.processed_feed.get_effective_digest_model(), "claude-3-sonnet")

    def test_global_other_model_empty_returns_none(self):
        """Test that 'other' selection with empty value returns None"""
        # Create AppSetting with 'other' but no actual model specified
        AppSetting.objects.create(
            global_summary_model="other",
            global_other_summary_model="",  # Empty
            global_digest_model="other",
            global_other_digest_model="",  # Empty
        )

        # Should return None when 'other' is selected but not specified
        self.assertIsNone(self.processed_feed.get_effective_summary_model())
        self.assertIsNone(self.processed_feed.get_effective_digest_model())

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def test_feed_other_model_selection(self, mock_async_update):
        """Test that 'other' selection in feed settings works correctly"""
        # Create AppSetting with models (AI enabled)
        AppSetting.objects.create(
            global_summary_model="gpt-5-nano",
            global_digest_model="gpt-5-mini",
        )

        # Set feed to use 'other' with custom models
        self.processed_feed.model = "other"
        self.processed_feed.other_model = "custom-model-1"
        self.processed_feed.digest_model = "other"
        self.processed_feed.other_digest_model = "custom-model-2"
        self.processed_feed.save()

        # Feed should return the custom 'other' models
        self.assertEqual(self.processed_feed.get_effective_summary_model(), "custom-model-1")
        self.assertEqual(self.processed_feed.get_effective_digest_model(), "custom-model-2")

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def test_feed_other_model_empty_returns_none(self, mock_async_update):
        """Test that feed 'other' selection with empty value returns None"""
        # Create AppSetting with models (AI enabled)
        AppSetting.objects.create(
            global_summary_model="gpt-5-nano",
            global_digest_model="gpt-5-mini",
        )

        # Set feed to use 'other' but with empty values
        self.processed_feed.model = "other"
        self.processed_feed.other_model = ""  # Empty
        self.processed_feed.digest_model = "other"
        self.processed_feed.other_digest_model = ""  # Empty
        self.processed_feed.save()

        # Should return None when 'other' is selected but not specified
        self.assertIsNone(self.processed_feed.get_effective_summary_model())
        self.assertIsNone(self.processed_feed.get_effective_digest_model())

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def test_no_app_setting_returns_none(self, mock_async_update):
        """Test that no AppSetting instance returns None (AI disabled)"""
        # No AppSetting created - should return None
        self.assertIsNone(self.processed_feed.get_effective_summary_model())
        self.assertIsNone(self.processed_feed.get_effective_digest_model())

        # Even with individual settings, should still return None (no global setting = AI off)
        self.processed_feed.model = "gpt-5-nano"
        self.processed_feed.digest_model = "gpt-5-mini"
        self.processed_feed.save()

        self.assertIsNone(self.processed_feed.get_effective_summary_model())
        self.assertIsNone(self.processed_feed.get_effective_digest_model())

    def test_global_methods_directly(self):
        """Test AppSetting class methods directly"""
        # Test with no AppSetting instance
        self.assertIsNone(AppSetting.get_global_summary_model())
        self.assertIsNone(AppSetting.get_global_digest_model())

        # Create AppSetting with 'none'
        app_setting = AppSetting.objects.create(
            global_summary_model="none",
            global_digest_model="none",
        )
        self.assertIsNone(AppSetting.get_global_summary_model())
        self.assertIsNone(AppSetting.get_global_digest_model())

        # Update to specific models
        app_setting.global_summary_model = "gpt-5-nano"
        app_setting.global_digest_model = "gpt-5-mini"
        app_setting.save()
        self.assertEqual(AppSetting.get_global_summary_model(), "gpt-5-nano")
        self.assertEqual(AppSetting.get_global_digest_model(), "gpt-5-mini")

        # Update to 'other' with values
        app_setting.global_summary_model = "other"
        app_setting.global_other_summary_model = "custom-summary"
        app_setting.global_digest_model = "other"
        app_setting.global_other_digest_model = "custom-digest"
        app_setting.save()
        self.assertEqual(AppSetting.get_global_summary_model(), "custom-summary")
        self.assertEqual(AppSetting.get_global_digest_model(), "custom-digest")

        # Update to 'other' without values
        app_setting.global_other_summary_model = ""
        app_setting.global_other_digest_model = ""
        app_setting.save()
        self.assertIsNone(AppSetting.get_global_summary_model())
        self.assertIsNone(AppSetting.get_global_digest_model())

    def test_app_setting_singleton(self):
        """Test that AppSetting enforces singleton pattern"""
        # Create first instance
        first_setting = AppSetting.objects.create(
            global_summary_model="gpt-5-nano",
            global_digest_model="gpt-5-mini",
            auth_code="first",
        )

        # Attempt to create second instance should update the existing one
        second_setting = AppSetting(
            global_summary_model="gpt-4o",
            global_digest_model="gpt-4o-mini",
            auth_code="second",
        )
        second_setting.save()

        # Verify only one instance exists
        self.assertEqual(AppSetting.objects.count(), 1)

        # The existing instance should have been updated with new values
        updated_setting = AppSetting.objects.first()
        self.assertIsNotNone(updated_setting)
        if updated_setting:  # Type guard for mypy
            self.assertEqual(updated_setting.global_summary_model, "gpt-4o")
            self.assertEqual(updated_setting.global_digest_model, "gpt-4o-mini")
            self.assertEqual(updated_setting.auth_code, "second")

        # Updating existing instance should work normally
        first_setting.refresh_from_db()
        first_setting.global_summary_model = "gpt-5"
        first_setting.save()
        self.assertEqual(AppSetting.objects.count(), 1)

    def test_app_setting_get_instance(self):
        """Test the get_instance helper method"""
        # When no instance exists, should return None
        instance = AppSetting.get_instance()
        self.assertIsNone(instance)

        # Create an instance
        AppSetting.objects.create(pk=1, global_summary_model="gpt-5-nano", auth_code="test123")

        # Now get_instance should return it
        retrieved_instance = AppSetting.get_instance()
        self.assertIsNotNone(retrieved_instance)
        self.assertEqual(retrieved_instance.pk, 1)
        self.assertEqual(retrieved_instance.auth_code, "test123")

    def test_app_setting_get_or_create_instance(self):
        """Test the get_or_create_instance helper method"""
        # First call creates instance with defaults
        instance1 = AppSetting.get_or_create_instance()
        self.assertIsNotNone(instance1)
        self.assertEqual(instance1.global_summary_model, "none")
        self.assertEqual(instance1.pk, 1)

        # Second call returns same instance
        instance2 = AppSetting.get_or_create_instance()
        self.assertEqual(instance1.pk, instance2.pk)
        self.assertEqual(AppSetting.objects.count(), 1)

        # Modify and verify it's the same instance
        instance1.auth_code = "test456"
        instance1.save()
        instance3 = AppSetting.get_or_create_instance()
        self.assertEqual(instance3.auth_code, "test456")


class TestEmptyFilterGroups(TestCase):
    """Test that empty filter groups are handled correctly"""

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def setUp(self, mock_async_update):
        """Set up test data"""
        self.original_feed = OriginalFeed.objects.create(url="https://example.com/feed", title="Test Feed")

        self.processed_feed = ProcessedFeed.objects.create(
            name="test_empty_filters",
            feed_group_relational_operator="all",  # ALL groups must pass
        )
        self.processed_feed.feeds.add(self.original_feed)

        # Create test article
        self.article = Article.objects.create(
            original_feed=self.original_feed,
            title="Test Article",
            link="https://example.com/article",
            content="Test content",
            published_date=timezone.now(),
        )

    def test_empty_filter_group_with_any_operator(self):
        """Test that empty filter group with 'any' operator doesn't block all articles"""
        from .utils import passes_filters

        # Create an empty filter group with "any" operator
        # This used to block all articles because any([]) = False
        FilterGroup.objects.create(processed_feed=self.processed_feed, usage="feed_filter", relational_operator="any")

        # Article should still pass (empty filter groups are skipped)
        result = passes_filters(self.article, self.processed_feed, "feed_filter")
        self.assertTrue(result, "Empty filter group should not block articles")

    def test_mixed_empty_and_populated_filter_groups(self):
        """Test that empty filter groups are ignored when mixed with populated ones"""
        from .utils import passes_filters

        # Create an empty filter group
        FilterGroup.objects.create(processed_feed=self.processed_feed, usage="feed_filter", relational_operator="any")

        # Create a populated filter group that should pass
        populated_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed, usage="feed_filter", relational_operator="any"
        )
        Filter.objects.create(filter_group=populated_group, field="title", match_type="contains", value="Test")

        # Article should pass (empty group ignored, populated group passes)
        result = passes_filters(self.article, self.processed_feed, "feed_filter")
        self.assertTrue(result, "Empty filter groups should be ignored")

    def test_all_filter_groups_empty(self):
        """Test that all empty filter groups means no filtering"""
        from .utils import passes_filters

        # Create multiple empty filter groups
        for _ in range(3):
            FilterGroup.objects.create(
                processed_feed=self.processed_feed, usage="feed_filter", relational_operator="any"
            )

        # Article should pass (all empty groups = no filtering)
        result = passes_filters(self.article, self.processed_feed, "feed_filter")
        self.assertTrue(result, "All empty filter groups should mean no filtering")


class TestMaxArticlesPerFeed(TestCase):
    """Test the max_articles_per_feed setting and its effect on feed generation"""

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def setUp(self, mock_async_update):
        """Set up test data for max articles testing"""
        # Create original feeds
        self.original_feed1 = OriginalFeed.objects.create(
            url="https://example.com/feed1", title="Test Feed 1", max_articles_to_keep=100
        )
        self.original_feed2 = OriginalFeed.objects.create(
            url="https://example.com/feed2", title="Test Feed 2", max_articles_to_keep=100
        )

        # Create processed feed
        self.processed_feed = ProcessedFeed.objects.create(
            name="test_max_articles_feed",
            toggle_entries=True,
            toggle_digest=False,
            feed_group_relational_operator="any",  # Need this for filters to work
        )
        self.processed_feed.feeds.add(self.original_feed1, self.original_feed2)

        # Create many articles for testing (150 total)
        self.articles = []
        base_time = timezone.now()
        for i in range(150):
            # Alternate between feeds
            original_feed = self.original_feed1 if i % 2 == 0 else self.original_feed2
            article = Article.objects.create(
                original_feed=original_feed,
                title=f"Article {i}",
                link=f"https://example.com/article/{i}",
                published_date=base_time - timedelta(hours=i),
                content=f"Content for article {i}",
            )
            self.articles.append(article)

    def test_default_max_articles_limit(self):
        """Test that default limit of 100 articles is applied when no AppSetting exists"""
        from django.test import RequestFactory

        from .feeds import ProcessedAtomFeed

        # Create a request
        factory = RequestFactory()
        request = factory.get(f"/feeds/{self.processed_feed.name}/")

        # Create feed view instance
        feed_view = ProcessedAtomFeed()
        feed_obj = feed_view.get_object(request, feed_name=self.processed_feed.name)

        # Get items
        items = feed_view.items(feed_obj)

        # Should return 100 articles (default limit)
        self.assertEqual(len(items), 100)

        # Verify they are the most recent articles
        self.assertEqual(items[0].title, "Article 0")
        self.assertEqual(items[99].title, "Article 99")

    def test_custom_max_articles_limit(self):
        """Test that custom max_articles_per_feed setting is respected"""
        from django.test import RequestFactory

        from .feeds import ProcessedAtomFeed

        # Create AppSetting with custom limit
        AppSetting.objects.create(max_articles_per_feed=50)

        # Create a request
        factory = RequestFactory()
        request = factory.get(f"/feeds/{self.processed_feed.name}/")

        # Create feed view instance
        feed_view = ProcessedAtomFeed()
        feed_obj = feed_view.get_object(request, feed_name=self.processed_feed.name)

        # Get items
        items = feed_view.items(feed_obj)

        # Should return 50 articles (custom limit)
        self.assertEqual(len(items), 50)

        # Verify they are the most recent articles
        self.assertEqual(items[0].title, "Article 0")
        self.assertEqual(items[49].title, "Article 49")

    def test_max_articles_with_filters_simple(self):
        """Test with a simple contains filter first"""
        from django.test import RequestFactory

        from .feeds import ProcessedAtomFeed

        # Set a limit
        AppSetting.objects.create(max_articles_per_feed=30)

        # Create a simple filter that matches articles with "0" in title
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed, usage="feed_filter", relational_operator="any"
        )
        Filter.objects.create(filter_group=filter_group, field="title", match_type="contains", value="0")

        # Create a request
        factory = RequestFactory()
        request = factory.get(f"/feeds/{self.processed_feed.name}/")

        # Create feed view instance
        feed_view = ProcessedAtomFeed()
        feed_obj = feed_view.get_object(request, feed_name=self.processed_feed.name)

        # Get items
        items = feed_view.items(feed_obj)

        # There are 24 articles with "0" in title (0, 10, 20, ..., 140)
        self.assertEqual(len(items), 24)

    def test_max_articles_with_filters(self):
        """Test that max_articles works correctly with filters applied"""
        from django.test import RequestFactory

        from .feeds import ProcessedAtomFeed

        # Set a limit
        AppSetting.objects.create(max_articles_per_feed=25)

        # Create a simple filter that matches articles with "1" in the title
        # This will match: 1, 10-19, 21, 31, 41, 51, 61, 71, 81, 91, 100-119, 120-129, 130-139, 140-149
        # Total matching: 1 + 10 + 9*1 + 20 + 10 = 50 articles
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed, usage="feed_filter", relational_operator="any"
        )
        Filter.objects.create(filter_group=filter_group, field="title", match_type="contains", value="1")

        # Create a request
        factory = RequestFactory()
        request = factory.get(f"/feeds/{self.processed_feed.name}/")

        # Create feed view instance
        feed_view = ProcessedAtomFeed()
        feed_obj = feed_view.get_object(request, feed_name=self.processed_feed.name)

        # Get items
        items = feed_view.items(feed_obj)

        # Should return 25 articles (limited by max_articles_per_feed)
        self.assertEqual(len(items), 25)

        # All articles should contain "1" in their titles
        for item in items:
            self.assertIn("1", item.title, f"Article {item.title} should contain '1'")

    def test_max_articles_with_regex_filters(self):
        """Test that max_articles works correctly with regex filters"""
        from django.test import RequestFactory

        from .feeds import ProcessedAtomFeed

        # Set a limit
        AppSetting.objects.create(max_articles_per_feed=30)

        # Create a regex filter for even-numbered articles
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed, usage="feed_filter", relational_operator="any"
        )
        Filter.objects.create(
            filter_group=filter_group,
            field="title",
            match_type="matches_regex",
            value="Article [0-9]*[02468]\\s*$",  # Matches even articles, allows trailing whitespace
        )

        # Create a request
        factory = RequestFactory()
        request = factory.get(f"/feeds/{self.processed_feed.name}/")

        # Create feed view instance
        feed_view = ProcessedAtomFeed()
        feed_obj = feed_view.get_object(request, feed_name=self.processed_feed.name)

        # Get items
        items = feed_view.items(feed_obj)

        # We have 75 even-numbered articles (0, 2, 4, ..., 148)
        # Should return 30 due to max_articles_per_feed limit
        self.assertEqual(len(items), 30)

        # Verify all returned articles are even-numbered
        for item in items:
            article_num = int(item.title.split()[1])
            self.assertEqual(article_num % 2, 0, f"Article {article_num} should be even")

        # Verify they are the most recent even articles
        self.assertEqual(items[0].title, "Article 0")
        self.assertEqual(items[1].title, "Article 2")
        self.assertEqual(items[29].title, "Article 58")

    def test_max_articles_with_duplicates(self):
        """Test that duplicate URLs are filtered out before applying max_articles limit"""
        from django.test import RequestFactory

        from .feeds import ProcessedAtomFeed

        # Create duplicate articles with same URL but from different feeds
        # (since there's a unique constraint on link+original_feed)
        duplicate_url = "https://example.com/duplicate"
        Article.objects.create(
            original_feed=self.original_feed1,
            title="Duplicate from Feed 1",
            link=duplicate_url,
            published_date=timezone.now() + timedelta(hours=1),
            content="Duplicate content from feed 1",
        )
        Article.objects.create(
            original_feed=self.original_feed2,
            title="Duplicate from Feed 2",
            link=duplicate_url,
            published_date=timezone.now() + timedelta(hours=2),
            content="Duplicate content from feed 2",
        )

        # Set a limit
        AppSetting.objects.create(max_articles_per_feed=100)

        # Create a request
        factory = RequestFactory()
        request = factory.get(f"/feeds/{self.processed_feed.name}/")

        # Create feed view instance
        feed_view = ProcessedAtomFeed()
        feed_obj = feed_view.get_object(request, feed_name=self.processed_feed.name)

        # Get items
        items = feed_view.items(feed_obj)

        # Should return 100 unique articles (the duplicate URL should appear only once)
        self.assertEqual(len(items), 100)

        # Count how many times the duplicate URL appears
        duplicate_count = sum(1 for item in items if item.link == "https://example.com/duplicate")
        self.assertEqual(duplicate_count, 1, "Duplicate URL should appear only once")

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def test_max_articles_with_digest_enabled(self, mock_async_update):
        """Test that digest entry doesn't count toward max_articles limit"""
        from django.test import RequestFactory

        from .feeds import ProcessedAtomFeed
        from .models import Digest

        # Enable digest
        self.processed_feed.toggle_digest = True
        self.processed_feed.save()

        # Create a digest
        Digest.objects.create(
            processed_feed=self.processed_feed,
            content="Test digest content",
            start_time=timezone.now() - timedelta(days=1),
        )

        # Set a limit
        AppSetting.objects.create(max_articles_per_feed=50)

        # Create a request
        factory = RequestFactory()
        request = factory.get(f"/feeds/{self.processed_feed.name}/")

        # Create feed view instance
        feed_view = ProcessedAtomFeed()
        feed_obj = feed_view.get_object(request, feed_name=self.processed_feed.name)

        # Get items
        items = feed_view.items(feed_obj)

        # Should return 51 items (1 digest + 50 articles)
        self.assertEqual(len(items), 51)

        # First item should be the digest
        self.assertIn("Digest for", items[0].title)

        # Rest should be articles
        self.assertEqual(items[1].title, "Article 0")
        self.assertEqual(items[50].title, "Article 49")

    def test_get_max_articles_per_feed_method(self):
        """Test the AppSetting.get_max_articles_per_feed() method"""
        # Test default when no AppSetting exists
        self.assertEqual(AppSetting.get_max_articles_per_feed(), 100)

        # Create AppSetting with custom value
        AppSetting.objects.create(max_articles_per_feed=200)
        self.assertEqual(AppSetting.get_max_articles_per_feed(), 200)

        # Update the value
        app_setting = AppSetting.objects.first()
        if app_setting:
            app_setting.max_articles_per_feed = 75
            app_setting.save()
        self.assertEqual(AppSetting.get_max_articles_per_feed(), 75)

    def test_max_articles_with_insufficient_articles(self):
        """Test behavior when there are fewer articles than the max limit"""
        from django.test import RequestFactory

        from .feeds import ProcessedAtomFeed

        # Delete most articles, keep only 20
        Article.objects.filter(id__in=[a.id for a in self.articles[20:]]).delete()

        # Set a high limit
        AppSetting.objects.create(max_articles_per_feed=200)

        # Create a request
        factory = RequestFactory()
        request = factory.get(f"/feeds/{self.processed_feed.name}/")

        # Create feed view instance
        feed_view = ProcessedAtomFeed()
        feed_obj = feed_view.get_object(request, feed_name=self.processed_feed.name)

        # Get items
        items = feed_view.items(feed_obj)

        # Should return all 20 available articles
        self.assertEqual(len(items), 20)


class TestProcessedFeedSaveAndResetBehavior(TestCase):
    """Test ProcessedFeed save behavior and m2m signal reset functionality"""

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def setUp(self, mock_async_update):
        """Set up test data"""
        from datetime import timedelta

        from django.utils import timezone

        # Create original feeds
        self.feed1 = OriginalFeed.objects.create(
            url="https://example1.com/feed.xml",
            title="Test Feed 1",
        )
        self.feed2 = OriginalFeed.objects.create(
            url="https://example2.com/feed.xml",
            title="Test Feed 2",
        )
        self.feed3 = OriginalFeed.objects.create(
            url="https://example3.com/feed.xml",
            title="Test Feed 3",
        )

        # Create processed feed with initial feeds
        self.processed_feed = ProcessedFeed.objects.create(
            name="test-processed-feed",
            toggle_digest=True,
            toggle_entries=True,
        )
        self.processed_feed.feeds.set([self.feed1, self.feed2])

        # Set initial timestamps
        self.initial_modified = timezone.now() - timedelta(days=2)
        self.initial_digest = timezone.now() - timedelta(days=1)
        ProcessedFeed.objects.filter(pk=self.processed_feed.pk).update(
            last_modified=self.initial_modified, last_digest=self.initial_digest
        )
        self.processed_feed.refresh_from_db()

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def test_save_without_m2m_changes_preserves_timestamps(self, mock_async_update):
        """Test that saving without changing feeds preserves last_modified and last_digest"""
        # Save the processed feed without changing feeds
        self.processed_feed.toggle_entries = False
        self.processed_feed.save()

        # Refresh and check timestamps are preserved
        self.processed_feed.refresh_from_db()
        self.assertEqual(self.processed_feed.last_modified, self.initial_modified)
        self.assertEqual(self.processed_feed.last_digest, self.initial_digest)
        self.assertFalse(self.processed_feed.toggle_entries)

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def test_manual_timestamp_change_without_m2m_changes(self, mock_async_update):
        """Test that manually changing timestamps works when not changing feeds"""
        from datetime import timedelta

        from django.utils import timezone

        new_digest_time = timezone.now() - timedelta(hours=6)
        new_modified_time = timezone.now() - timedelta(hours=12)

        # Update timestamps manually
        self.processed_feed.last_digest = new_digest_time
        self.processed_feed.last_modified = new_modified_time
        self.processed_feed.save()

        # Verify the manual changes persisted
        self.processed_feed.refresh_from_db()
        self.assertEqual(self.processed_feed.last_digest, new_digest_time)
        self.assertEqual(self.processed_feed.last_modified, new_modified_time)

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def test_adding_feed_resets_timestamps(self, mock_async_update):
        """Test that adding a feed resets last_modified and last_digest"""
        # Add a new feed
        self.processed_feed.feeds.add(self.feed3)

        # Check that timestamps were reset
        self.processed_feed.refresh_from_db()
        self.assertIsNone(self.processed_feed.last_modified)
        self.assertIsNone(self.processed_feed.last_digest)

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def test_removing_feed_resets_timestamps(self, mock_async_update):
        """Test that removing a feed resets last_modified and last_digest"""
        # Remove a feed
        self.processed_feed.feeds.remove(self.feed1)

        # Check that timestamps were reset
        self.processed_feed.refresh_from_db()
        self.assertIsNone(self.processed_feed.last_modified)
        self.assertIsNone(self.processed_feed.last_digest)

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def test_clearing_feeds_resets_timestamps(self, mock_async_update):
        """Test that clearing all feeds resets last_modified and last_digest"""
        # Clear all feeds
        self.processed_feed.feeds.clear()

        # Check that timestamps were reset
        self.processed_feed.refresh_from_db()
        self.assertIsNone(self.processed_feed.last_modified)
        self.assertIsNone(self.processed_feed.last_digest)

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def test_setting_same_feeds_preserves_timestamps(self, mock_async_update):
        """Test that setting the same feeds doesn't reset timestamps"""
        # Get current feeds
        current_feeds = list(self.processed_feed.feeds.all())

        # Set the same feeds again
        self.processed_feed.feeds.set(current_feeds)

        # Timestamps should be preserved (no actual change)
        self.processed_feed.refresh_from_db()
        self.assertEqual(self.processed_feed.last_modified, self.initial_modified)
        self.assertEqual(self.processed_feed.last_digest, self.initial_digest)

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def test_multiple_saves_without_m2m_changes(self, mock_async_update):
        """Test multiple saves in succession without m2m changes"""
        from datetime import timedelta

        from django.utils import timezone

        # First save with timestamp changes
        time1 = timezone.now() - timedelta(hours=5)
        self.processed_feed.last_digest = time1
        self.processed_feed.save()

        # Second save with different field change
        self.processed_feed.refresh_from_db()
        self.processed_feed.summary_language = "zh"
        self.processed_feed.save()

        # Third save with another timestamp change
        self.processed_feed.refresh_from_db()
        time2 = timezone.now() - timedelta(hours=3)
        self.processed_feed.last_modified = time2
        self.processed_feed.save()

        # Verify all changes persisted
        self.processed_feed.refresh_from_db()
        self.assertEqual(self.processed_feed.last_digest, time1)
        self.assertEqual(self.processed_feed.last_modified, time2)
        self.assertEqual(self.processed_feed.summary_language, "zh")

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def test_admin_form_scenario_no_feed_change(self, mock_async_update):
        """Simulate admin form save without feed changes"""
        # Simulate what happens in admin when saving without changing feeds
        # This tests the scenario where Django admin might trigger m2m signals
        # even when feeds haven't actually changed

        # Store original values
        original_feeds = list(self.processed_feed.feeds.values_list("pk", flat=True))

        # Simulate form save with same feeds
        self.processed_feed.toggle_digest = False
        self.processed_feed.save()

        # Re-set the same feeds (simulating admin form behavior)
        self.processed_feed.feeds.set(original_feeds)

        # Timestamps should be preserved
        self.processed_feed.refresh_from_db()
        self.assertEqual(self.processed_feed.last_modified, self.initial_modified)
        self.assertEqual(self.processed_feed.last_digest, self.initial_digest)
        self.assertFalse(self.processed_feed.toggle_digest)

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def test_save_triggers_async_update(self, mock_async_update):
        """Test that save() triggers async_update_feeds_and_digest"""
        self.processed_feed.save()
        mock_async_update.schedule.assert_called_once_with(args=(self.processed_feed.name,), delay=1)

    @patch("FeedManager.models.async_update_feeds_and_digest")
    def test_reset_only_on_actual_feed_changes(self, mock_async_update):
        """Test that timestamps only reset when feeds actually change"""
        from datetime import timedelta

        from django.utils import timezone

        # Set custom timestamps
        custom_time = timezone.now() - timedelta(hours=2)
        self.processed_feed.last_digest = custom_time
        self.processed_feed.save()

        # Verify saved correctly
        self.processed_feed.refresh_from_db()
        self.assertEqual(self.processed_feed.last_digest, custom_time)

        # Now actually change feeds
        self.processed_feed.feeds.add(self.feed3)

        # Now timestamps should be reset
        self.processed_feed.refresh_from_db()
        self.assertIsNone(self.processed_feed.last_digest)
        self.assertIsNone(self.processed_feed.last_modified)


class TestTagBasedFeedInclusion(TestCase):
    @patch("FeedManager.models.async_update_feeds_and_digest")
    def setUp(self, mock_async_update):
        """Set up test data for tag-based feed inclusion tests"""
        # Create tags
        self.tag_tech = Tag.objects.create(name="tech")
        self.tag_news = Tag.objects.create(name="news")
        self.tag_science = Tag.objects.create(name="science")

        # Create original feeds with different tags
        self.feed_tech1 = OriginalFeed.objects.create(
            url="https://techfeed1.com/rss",
            title="Tech Feed 1",
        )
        self.feed_tech1.tags.add(self.tag_tech)

        self.feed_tech2 = OriginalFeed.objects.create(
            url="https://techfeed2.com/rss",
            title="Tech Feed 2",
        )
        self.feed_tech2.tags.add(self.tag_tech)

        self.feed_news = OriginalFeed.objects.create(
            url="https://newsfeed.com/rss",
            title="News Feed",
        )
        self.feed_news.tags.add(self.tag_news)

        self.feed_multi_tag = OriginalFeed.objects.create(
            url="https://multifeed.com/rss",
            title="Multi Tag Feed",
        )
        self.feed_multi_tag.tags.add(self.tag_tech, self.tag_science)

        self.feed_no_tag = OriginalFeed.objects.create(
            url="https://notag.com/rss",
            title="No Tag Feed",
        )

        # Create a processed feed
        self.processed_feed = ProcessedFeed.objects.create(
            name="test_tag_feed",
        )

    def test_get_all_feeds_with_no_tags_selected(self):
        """Test get_all_feeds returns only directly selected feeds when no tags are selected"""
        self.processed_feed.feeds.add(self.feed_no_tag)

        all_feeds = self.processed_feed.get_all_feeds()

        self.assertEqual(len(all_feeds), 1)
        self.assertIn(self.feed_no_tag, all_feeds)

    def test_get_all_feeds_with_single_tag(self):
        """Test get_all_feeds includes all feeds with selected tag"""
        self.processed_feed.include_tags.add(self.tag_tech)

        all_feeds = self.processed_feed.get_all_feeds()

        # Should include both tech feeds and the multi-tag feed
        self.assertEqual(len(all_feeds), 3)
        self.assertIn(self.feed_tech1, all_feeds)
        self.assertIn(self.feed_tech2, all_feeds)
        self.assertIn(self.feed_multi_tag, all_feeds)

    def test_get_all_feeds_with_multiple_tags(self):
        """Test get_all_feeds includes feeds from multiple tags"""
        self.processed_feed.include_tags.add(self.tag_tech, self.tag_news)

        all_feeds = self.processed_feed.get_all_feeds()

        # Should include tech feeds, news feed, and multi-tag feed
        self.assertEqual(len(all_feeds), 4)
        self.assertIn(self.feed_tech1, all_feeds)
        self.assertIn(self.feed_tech2, all_feeds)
        self.assertIn(self.feed_news, all_feeds)
        self.assertIn(self.feed_multi_tag, all_feeds)

    def test_get_all_feeds_combines_direct_and_tag_feeds(self):
        """Test get_all_feeds combines directly selected and tag-selected feeds"""
        # Add one feed directly
        self.processed_feed.feeds.add(self.feed_no_tag)
        # Add tech tag to get tech feeds
        self.processed_feed.include_tags.add(self.tag_tech)

        all_feeds = self.processed_feed.get_all_feeds()

        # Should include directly selected feed plus tech feeds
        self.assertEqual(len(all_feeds), 4)
        self.assertIn(self.feed_no_tag, all_feeds)
        self.assertIn(self.feed_tech1, all_feeds)
        self.assertIn(self.feed_tech2, all_feeds)
        self.assertIn(self.feed_multi_tag, all_feeds)

    def test_get_all_feeds_no_duplicates(self):
        """Test get_all_feeds doesn't include duplicates when feed is both direct and tag-selected"""
        # Add tech1 feed directly
        self.processed_feed.feeds.add(self.feed_tech1)
        # Also add tech tag which includes tech1
        self.processed_feed.include_tags.add(self.tag_tech)

        all_feeds = self.processed_feed.get_all_feeds()

        # Should not have duplicates
        self.assertEqual(len(all_feeds), 3)
        self.assertIn(self.feed_tech1, all_feeds)
        self.assertIn(self.feed_tech2, all_feeds)
        self.assertIn(self.feed_multi_tag, all_feeds)

        # Verify feed_tech1 appears only once
        feed_count = list(all_feeds).count(self.feed_tech1)
        self.assertEqual(feed_count, 1)

    @patch("FeedManager.models.ProcessedFeed.objects.filter")
    def test_tags_change_resets_timestamps(self, mock_filter):
        """Test that adding/removing tags resets last_modified and last_digest"""
        from datetime import timedelta

        from django.utils import timezone

        # Set up mock to track update calls
        mock_update = MagicMock()
        mock_filter.return_value.update = mock_update

        # Set initial timestamps
        initial_time = timezone.now() - timedelta(days=1)
        ProcessedFeed.objects.filter(pk=self.processed_feed.pk).update(
            last_modified=initial_time,
            last_digest=initial_time
        )

        # Add a tag - should trigger reset
        self.processed_feed.include_tags.add(self.tag_tech)

        # Verify update was called with None values
        mock_update.assert_called_with(last_modified=None, last_digest=None)

        # Reset mock
        mock_update.reset_mock()

        # Remove the tag - should also trigger reset
        self.processed_feed.include_tags.remove(self.tag_tech)

        # Verify update was called again
        mock_update.assert_called_with(last_modified=None, last_digest=None)

    def test_empty_tags_returns_only_direct_feeds(self):
        """Test that empty include_tags doesn't affect feed selection"""
        # Add some direct feeds
        self.processed_feed.feeds.add(self.feed_tech1, self.feed_news)

        all_feeds = self.processed_feed.get_all_feeds()

        # Should only have the directly selected feeds
        self.assertEqual(len(all_feeds), 2)
        self.assertIn(self.feed_tech1, all_feeds)
        self.assertIn(self.feed_news, all_feeds)
        self.assertNotIn(self.feed_tech2, all_feeds)  # Not included via tag

    @patch("FeedManager.models.async_update_feeds_and_digest.schedule")
    def test_validation_requires_feed_or_tag(self, mock_schedule):
        """Test that validation requires at least one feed or tag to be selected"""
        from django.core.exceptions import ValidationError

        # Create and save a ProcessedFeed without feeds or tags
        invalid_feed = ProcessedFeed.objects.create(
            name="invalid_feed",
            toggle_digest=True,
            toggle_entries=True,
        )

        # This should raise a ValidationError
        with self.assertRaises(ValidationError) as context:
            invalid_feed.clean()

        self.assertIn("At least one original feed or tag must be selected", str(context.exception))

    @patch("FeedManager.models.async_update_feeds_and_digest.schedule")
    def test_validation_passes_with_only_tags(self, mock_schedule):
        """Test that validation passes with only tags selected"""
        from django.core.exceptions import ValidationError

        # Create a ProcessedFeed with only tags
        valid_feed = ProcessedFeed.objects.create(
            name="tag_only_feed",
            toggle_digest=True,
            toggle_entries=True,
        )
        valid_feed.include_tags.add(self.tag_tech)

        # This should not raise an error
        try:
            valid_feed.clean()
        except ValidationError:
            self.fail("Validation should pass with tags selected")

    @patch("FeedManager.models.async_update_feeds_and_digest.schedule")
    def test_validation_passes_with_only_feeds(self, mock_schedule):
        """Test that validation passes with only feeds selected"""
        from django.core.exceptions import ValidationError

        # Create a ProcessedFeed with only feeds
        valid_feed = ProcessedFeed.objects.create(
            name="feed_only_feed",
            toggle_digest=True,
            toggle_entries=True,
        )
        valid_feed.feeds.add(self.feed_tech1)

        # This should not raise an error
        try:
            valid_feed.clean()
        except ValidationError:
            self.fail("Validation should pass with feeds selected")


class TestOPMLImportExport(TestCase):
    def test_import_opml_with_nested_folders_generates_tags(self):
        import io

        from FeedManager.models import OriginalFeed, Tag
        from FeedManager.opml import import_original_feeds_from_opml

        opml = """
        <opml version=\"2.0\">
          <head><title>Test</title></head>
          <body>
            <outline text=\"Tech\">
              <outline text=\"AI\">
                <outline text=\"OpenAI Blog\" type=\"rss\" xmlUrl=\"https://example.com/openai.xml\" />
              </outline>
              <outline text=\"Dev\">
                <outline text=\"Django News\" type=\"rss\" xmlUrl=\"https://example.com/django.xml\" />
              </outline>
            </outline>
            <outline text=\"Untagged\" type=\"rss\" xmlUrl=\"https://example.com/untagged.xml\" />
          </body>
        </opml>
        """
        result = import_original_feeds_from_opml(io.StringIO(opml))
        self.assertEqual(result.feeds_seen, 3)
        self.assertEqual(OriginalFeed.objects.count(), 3)

        openai = OriginalFeed.objects.get(url="https://example.com/openai.xml")
        django = OriginalFeed.objects.get(url="https://example.com/django.xml")
        untagged = OriginalFeed.objects.get(url="https://example.com/untagged.xml")

        tags = set(Tag.objects.values_list("name", flat=True))
        self.assertTrue({"Tech", "AI", "Dev"}.issubset(tags))

        self.assertEqual(set(openai.tags.values_list("name", flat=True)), {"Tech", "AI"})
        self.assertEqual(set(django.tags.values_list("name", flat=True)), {"Tech", "Dev"})
        self.assertEqual(set(untagged.tags.values_list("name", flat=True)), set())

    def test_export_grouped_by_tags(self):
        from defusedxml import ElementTree as SafeET

        from FeedManager.models import OriginalFeed, Tag
        from FeedManager.opml import export_original_feeds_as_opml

        feed1 = OriginalFeed.objects.create(url="https://a.com/1.xml", title="One")
        feed2 = OriginalFeed.objects.create(url="https://a.com/2.xml", title="Two")
        t_ai = Tag.objects.create(name="AI")
        t_dev = Tag.objects.create(name="Dev")
        feed1.tags.add(t_ai)
        feed2.tags.add(t_ai, t_dev)

        xml = export_original_feeds_as_opml(OriginalFeed.objects.all(), group_by_tags=True)
        tree = SafeET.fromstring(xml)
        body = tree.find("body")
        self.assertIsNotNone(body)

        # Expect top-level outlines for tag folders
        folder_names = [n.attrib.get("text") for n in body.findall("outline") if "xmlUrl" not in n.attrib]
        self.assertIn("AI", folder_names)
        self.assertIn("Dev", folder_names)

        # Inside AI folder both feeds should appear
        ai_node = next(n for n in body.findall("outline") if n.attrib.get("text") == "AI")
        ai_urls = {c.attrib.get("xmlUrl") for c in ai_node.findall("outline")}
        self.assertEqual(ai_urls, {"https://a.com/1.xml", "https://a.com/2.xml"})

        # Inside Dev folder feed2 should appear
        dev_node = next(n for n in body.findall("outline") if n.attrib.get("text") == "Dev")
        dev_urls = {c.attrib.get("xmlUrl") for c in dev_node.findall("outline")}
        self.assertEqual(dev_urls, {"https://a.com/2.xml"})

    def test_export_flat_includes_categories(self):
        from defusedxml import ElementTree as SafeET

        from FeedManager.models import OriginalFeed, Tag
        from FeedManager.opml import export_original_feeds_as_opml

        feed = OriginalFeed.objects.create(url="https://a.com/3.xml", title="Three")
        tag = Tag.objects.create(name="News")
        feed.tags.add(tag)
        xml = export_original_feeds_as_opml([feed], group_by_tags=False)
        tree = SafeET.fromstring(xml)
        body = tree.find("body")
        outlines = body.findall("outline")
        self.assertEqual(len(outlines), 1)
        self.assertEqual(outlines[0].attrib.get("category"), "News")
