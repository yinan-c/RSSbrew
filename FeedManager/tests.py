from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

import feedparser

from .models import Article, Filter, FilterGroup, OriginalFeed, ProcessedFeed
from .utils import match_content, passes_filters


class TestContentFilter(TestCase):
    @patch('FeedManager.models.async_update_feeds_and_digest')
    def setUp(self, mock_async_update):
        """Set up test data"""
        # Create a test user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass'
        )

        # Create an original feed
        self.original_feed = OriginalFeed.objects.create(
            url='https://lorem-rss.herokuapp.com/feed',
            title='Test Feed',
            max_articles_to_keep=100
        )

        # Create a processed feed
        self.processed_feed = ProcessedFeed.objects.create(
            name='test_processed_feed',
            feed_group_relational_operator='any',
            summary_group_relational_operator='any',
            case_sensitive=False
        )
        self.processed_feed.feeds.add(self.original_feed)

    def test_content_filter_with_article_object(self):
        """Test that content filters work correctly with Article objects from database"""

        # Create an article with Lorem in content
        article = Article.objects.create(
            original_feed=self.original_feed,
            title='Test Article',
            link='https://example.com/test',
            published_date=timezone.now(),
            content='Lorem ipsum dolor sit amet, consectetur adipiscing elit.'
        )

        # Create a filter group for feed filtering
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed,
            usage='feed_filter',
            relational_operator='any'
        )

        # Create a content filter for "Lorem"
        content_filter = Filter.objects.create(
            filter_group=filter_group,
            field='content',
            match_type='contains',
            value='Lorem'
        )

        # Test that the article passes the filter
        result = passes_filters(article, self.processed_feed, 'feed_filter')
        self.assertTrue(result, "Article with 'Lorem' in content should pass the filter")

    @patch('FeedManager.models.async_update_feeds_and_digest')
    def test_content_filter_case_insensitive(self, mock_async_update):
        """Test case-insensitive content filtering"""

        # Create an article with lowercase 'lorem' in content
        article = Article.objects.create(
            original_feed=self.original_feed,
            title='Test Article 2',
            link='https://example.com/test2',
            published_date=timezone.now(),
            content='lorem ipsum dolor sit amet, consectetur adipiscing elit.'
        )

        # Create a filter group
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed,
            usage='feed_filter',
            relational_operator='any'
        )

        # Create a content filter for "Lorem" (uppercase)
        content_filter = Filter.objects.create(
            filter_group=filter_group,
            field='content',
            match_type='contains',
            value='Lorem'
        )

        # Test with case-insensitive (default)
        result = passes_filters(article, self.processed_feed, 'feed_filter')
        self.assertTrue(result, "Article with 'lorem' should pass case-insensitive filter for 'Lorem'")

        # Test with case-sensitive
        self.processed_feed.case_sensitive = True
        self.processed_feed.save()
        result = passes_filters(article, self.processed_feed, 'feed_filter')
        self.assertFalse(result, "Article with 'lorem' should NOT pass case-sensitive filter for 'Lorem'")

    def test_content_filter_does_not_contain(self):
        """Test 'does not contain' filter type"""

        # Create two articles
        article_with_lorem = Article.objects.create(
            original_feed=self.original_feed,
            title='Article With Lorem',
            link='https://example.com/with-lorem',
            published_date=timezone.now(),
            content='Lorem ipsum dolor sit amet.'
        )

        article_without_lorem = Article.objects.create(
            original_feed=self.original_feed,
            title='Article Without Lorem',
            link='https://example.com/without-lorem',
            published_date=timezone.now(),
            content='This is just plain text without the keyword.'
        )

        # Create a filter group
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed,
            usage='feed_filter',
            relational_operator='any'
        )

        # Create a "does not contain" filter for "Lorem"
        content_filter = Filter.objects.create(
            filter_group=filter_group,
            field='content',
            match_type='does_not_contain',
            value='Lorem'
        )

        # Test both articles
        result_with = passes_filters(article_with_lorem, self.processed_feed, 'feed_filter')
        self.assertFalse(result_with, "Article with 'Lorem' should NOT pass 'does_not_contain' filter")

        result_without = passes_filters(article_without_lorem, self.processed_feed, 'feed_filter')
        self.assertTrue(result_without, "Article without 'Lorem' should pass 'does_not_contain' filter")

    def test_title_or_content_filter(self):
        """Test filters that check both title and content"""

        # Create articles with keyword in different places
        article_title_only = Article.objects.create(
            original_feed=self.original_feed,
            title='Lorem in Title',
            link='https://example.com/title-only',
            published_date=timezone.now(),
            content='This content does not have the keyword.'
        )

        article_content_only = Article.objects.create(
            original_feed=self.original_feed,
            title='Regular Title',
            link='https://example.com/content-only',
            published_date=timezone.now(),
            content='Lorem ipsum dolor sit amet.'
        )

        article_neither = Article.objects.create(
            original_feed=self.original_feed,
            title='Regular Title',
            link='https://example.com/neither',
            published_date=timezone.now(),
            content='Regular content without the keyword.'
        )

        # Create a filter group
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed,
            usage='feed_filter',
            relational_operator='any'
        )

        # Create a title_or_content filter for "Lorem"
        content_filter = Filter.objects.create(
            filter_group=filter_group,
            field='title_or_content',
            match_type='contains',
            value='Lorem'
        )

        # Test all three articles
        self.assertTrue(
            passes_filters(article_title_only, self.processed_feed, 'feed_filter'),
            "Article with 'Lorem' in title should pass title_or_content filter"
        )
        self.assertTrue(
            passes_filters(article_content_only, self.processed_feed, 'feed_filter'),
            "Article with 'Lorem' in content should pass title_or_content filter"
        )
        self.assertFalse(
            passes_filters(article_neither, self.processed_feed, 'feed_filter'),
            "Article without 'Lorem' anywhere should NOT pass title_or_content filter"
        )

    def test_empty_content_handling(self):
        """Test that articles with empty content are handled correctly"""

        # Create an article with no content
        article_no_content = Article.objects.create(
            original_feed=self.original_feed,
            title='Article With No Content',
            link='https://example.com/no-content',
            published_date=timezone.now(),
            content=''  # Empty content
        )

        # Create a filter group
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed,
            usage='feed_filter',
            relational_operator='any'
        )

        # Create a content filter for any keyword
        content_filter = Filter.objects.create(
            filter_group=filter_group,
            field='content',
            match_type='contains',
            value='Lorem'
        )

        # Article with empty content should not pass a "contains" filter
        result = passes_filters(article_no_content, self.processed_feed, 'feed_filter')
        self.assertFalse(result, "Article with empty content should not pass 'contains' filter")

    def test_match_content_direct(self):
        """Test the match_content function directly with Article objects"""

        # Create an article
        article = Article.objects.create(
            original_feed=self.original_feed,
            title='Test Direct Match',
            link='https://example.com/direct',
            published_date=timezone.now(),
            content='Lorem ipsum dolor sit amet.'
        )

        # Create a filter group (needed for filter)
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed,
            usage='feed_filter',
            relational_operator='any'
        )

        # Create a filter
        content_filter = Filter.objects.create(
            filter_group=filter_group,
            field='content',
            match_type='contains',
            value='Lorem'
        )

        # Test match_content directly
        result = match_content(article, content_filter, case_sensitive=False)
        self.assertTrue(result, "match_content should return True for Article with matching content")


class TestFeedparserContentFilter(TestCase):
    """Test content filtering with actual feedparser entries (not database objects)"""

    @patch('FeedManager.models.async_update_feeds_and_digest')
    def setUp(self, mock_async_update):
        """Set up test data"""
        # Create an original feed
        self.original_feed = OriginalFeed.objects.create(
            url='https://lorem-rss.herokuapp.com/feed?unit=second&interval=30',
            title='Lorem RSS Test Feed',
            max_articles_to_keep=100
        )

        # Create a processed feed
        self.processed_feed = ProcessedFeed.objects.create(
            name='lorem_test_feed',
            feed_group_relational_operator='any',
            summary_group_relational_operator='any',
            case_sensitive=False
        )
        self.processed_feed.feeds.add(self.original_feed)

        # Sample RSS content from the Lorem RSS feed
        self.rss_content = '''<?xml version="1.0" encoding="UTF-8"?><rss xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:atom="http://www.w3.org/2005/Atom" version="2.0"><channel><title><![CDATA[Lorem ipsum feed for an interval of 30 seconds with 10 item(s)]]></title><description><![CDATA[This is a constantly updating lorem ipsum feed]]></description><link>http://example.com/</link><generator>RSS for Node</generator><lastBuildDate>Tue, 19 Aug 2025 00:15:03 GMT</lastBuildDate><pubDate>Tue, 19 Aug 2025 00:15:00 GMT</pubDate><copyright><![CDATA[Michael Bertolacci, licensed under a Creative Commons Attribution 3.0 Unported License.]]></copyright><ttl>1</ttl><item><title><![CDATA[Lorem ipsum 2025-08-19T00:15:00Z]]></title><description><![CDATA[Id voluptate sunt in adipisicing occaecat amet mollit fugiat non sunt magna.]]></description><link>http://example.com/test/1755562500</link><guid isPermaLink="true">http://example.com/test/1755562500</guid><dc:creator><![CDATA[John Smith]]></dc:creator><pubDate>Tue, 19 Aug 2025 00:15:00 GMT</pubDate></item><item><title><![CDATA[Lorem ipsum 2025-08-19T00:14:30Z]]></title><description><![CDATA[Dolor aliqua ipsum non labore.]]></description><link>http://example.com/test/1755562470</link><guid isPermaLink="true">http://example.com/test/1755562470</guid><dc:creator><![CDATA[John Smith]]></dc:creator><pubDate>Tue, 19 Aug 2025 00:14:30 GMT</pubDate></item><item><title><![CDATA[Lorem ipsum 2025-08-19T00:14:00Z]]></title><description><![CDATA[Velit fugiat in irure ut adipisicing officia incididunt aute sunt.]]></description><link>http://example.com/test/1755562440</link><guid isPermaLink="true">http://example.com/test/1755562440</guid><dc:creator><![CDATA[John Smith]]></dc:creator><pubDate>Tue, 19 Aug 2025 00:14:00 GMT</pubDate></item></channel></rss>'''

    def test_feedparser_entry_content_filter(self):
        """Test that content filters work with feedparser entries"""

        # Parse the RSS feed
        feed = feedparser.parse(self.rss_content)

        # Create a filter group for feed filtering
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed,
            usage='feed_filter',
            relational_operator='any'
        )

        # Create a content filter for "Lorem" (appears in title)
        title_filter = Filter.objects.create(
            filter_group=filter_group,
            field='title',
            match_type='contains',
            value='Lorem'
        )

        # Test that entries with "Lorem" in title pass the filter
        for entry in feed.entries:
            result = passes_filters(entry, self.processed_feed, 'feed_filter')
            self.assertTrue(result, f"Entry with title '{entry.title}' should pass filter for 'Lorem'")

    def test_feedparser_description_filter(self):
        """Test filtering on description/content field with feedparser entries"""

        # Parse the RSS feed
        feed = feedparser.parse(self.rss_content)

        # Create a filter group
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed,
            usage='feed_filter',
            relational_operator='any'
        )

        # Create a content filter for "ipsum" (appears in some descriptions)
        content_filter = Filter.objects.create(
            filter_group=filter_group,
            field='content',
            match_type='contains',
            value='ipsum'
        )

        # Check each entry
        expected_results = [
            False,  # "Id voluptate sunt..." - no 'ipsum'
            True,   # "Dolor aliqua ipsum..." - has 'ipsum'
            False,  # "Velit fugiat in..." - no 'ipsum'
        ]

        for i, entry in enumerate(feed.entries[:3]):
            result = passes_filters(entry, self.processed_feed, 'feed_filter')
            self.assertEqual(result, expected_results[i],
                           f"Entry {i} with description '{entry.description}' should {'pass' if expected_results[i] else 'not pass'} filter for 'ipsum'")

    @patch('FeedManager.models.async_update_feeds_and_digest')
    def test_feedparser_case_sensitive_filter(self, mock_async_update):
        """Test case-sensitive filtering with feedparser entries"""

        # Parse the RSS feed
        feed = feedparser.parse(self.rss_content)

        # Create a filter group
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed,
            usage='feed_filter',
            relational_operator='any'
        )

        # Create a filter for "lorem" (lowercase)
        content_filter = Filter.objects.create(
            filter_group=filter_group,
            field='title',
            match_type='contains',
            value='lorem'  # lowercase
        )

        # With case-insensitive (default), should match "Lorem" in titles
        for entry in feed.entries:
            result = passes_filters(entry, self.processed_feed, 'feed_filter')
            self.assertTrue(result, f"Case-insensitive: Entry with title '{entry.title}' should pass filter for 'lorem'")

        # Enable case-sensitive
        self.processed_feed.case_sensitive = True
        self.processed_feed.save()

        # Now it should NOT match because titles have "Lorem" (capital L)
        for entry in feed.entries:
            result = passes_filters(entry, self.processed_feed, 'feed_filter')
            self.assertFalse(result, f"Case-sensitive: Entry with title '{entry.title}' should NOT pass filter for 'lorem' (lowercase)")

    def test_feedparser_title_or_content_filter(self):
        """Test title_or_content filtering with feedparser entries"""

        # Parse the RSS feed
        feed = feedparser.parse(self.rss_content)

        # Create a filter group
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed,
            usage='feed_filter',
            relational_operator='any'
        )

        # Create a title_or_content filter for "adipisicing"
        # This word appears in some descriptions but not in titles
        content_filter = Filter.objects.create(
            filter_group=filter_group,
            field='title_or_content',
            match_type='contains',
            value='adipisicing'
        )

        # Check entries
        # First entry has "adipisicing" in description
        # Second entry doesn't have it
        # Third entry has "adipisicing" in description
        expected_results = [
            True,   # "Id voluptate sunt in adipisicing..."
            False,  # "Dolor aliqua ipsum non labore."
            True,   # "Velit fugiat in irure ut adipisicing..."
        ]

        for i, entry in enumerate(feed.entries[:3]):
            result = passes_filters(entry, self.processed_feed, 'feed_filter')
            self.assertEqual(result, expected_results[i],
                           f"Entry {i} should {'pass' if expected_results[i] else 'not pass'} filter for 'adipisicing'")

    def test_feedparser_does_not_contain_filter(self):
        """Test 'does not contain' filter with feedparser entries"""

        # Parse the RSS feed
        feed = feedparser.parse(self.rss_content)

        # Create a filter group
        filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed,
            usage='feed_filter',
            relational_operator='any'
        )

        # Create a "does not contain" filter for "ipsum"
        content_filter = Filter.objects.create(
            filter_group=filter_group,
            field='content',
            match_type='does_not_contain',
            value='ipsum'
        )

        # Check entries - opposite of the contains test
        expected_results = [
            True,   # "Id voluptate sunt..." - no 'ipsum'
            False,  # "Dolor aliqua ipsum..." - has 'ipsum'
            True,   # "Velit fugiat in..." - no 'ipsum'
        ]

        for i, entry in enumerate(feed.entries[:3]):
            result = passes_filters(entry, self.processed_feed, 'feed_filter')
            self.assertEqual(result, expected_results[i],
                           f"Entry {i} should {'pass' if expected_results[i] else 'not pass'} 'does_not_contain' filter for 'ipsum'")

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
                        'type': 'html',
                        'value': '&lt;!-- TEST_OFF --&gt;&lt;div class=&quot;content&quot;&gt;&lt;p&gt;Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.&lt;/p&gt;&lt;/div&gt;&lt;!-- TEST_ON --&gt;'
                    }
                ]

        entry = MockHtmlEntry()

        # Create filter group with test keywords that appear in HTML comments
        test_filter_group = FilterGroup.objects.create(
            processed_feed=self.processed_feed,
            usage='feed_filter',
            relational_operator='any'
        )

        # Create filters for keywords that could appear in HTML comments/markup
        test_keywords = ['test', 'off', 'on', 'div', 'content']
        for keyword in test_keywords:
            Filter.objects.create(
                filter_group=test_filter_group,
                field='title_or_content',
                match_type='contains',
                value=keyword
            )

        # Import clean_html to analyze the difference
        from .utils import clean_html

        # Build content strings for comparison
        raw_content = entry.title + ' ' + entry.content[0]['value']
        cleaned_content = entry.title + ' ' + clean_html(entry.content[0]['value'])

        # Check if problematic keywords exist in raw vs cleaned content
        raw_has_keywords = any(keyword in raw_content.lower() for keyword in ['off', 'test', 'div'])
        cleaned_has_keywords = any(keyword in cleaned_content.lower() for keyword in ['off', 'test', 'div'])

        # Test the filter result
        result = passes_filters(entry, self.processed_feed, 'feed_filter')

        # Verify the fix: raw content should have HTML keywords but cleaned shouldn't
        self.assertTrue(raw_has_keywords, "Raw HTML content should contain markup keywords")
        self.assertFalse(cleaned_has_keywords, "Cleaned content should not contain HTML markup keywords")

        # The entry should NOT be included since it only matches HTML markup, not actual content
        self.assertFalse(result,
                        "Entry should NOT pass filters when keywords only exist in HTML markup")
