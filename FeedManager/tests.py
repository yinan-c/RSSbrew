from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

import feedparser

from .models import AppSetting, Article, Filter, FilterGroup, OriginalFeed, ProcessedFeed
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
