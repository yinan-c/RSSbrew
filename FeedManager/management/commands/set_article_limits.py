"""
Management command to safely update max_articles_to_keep for all feeds
and optionally clean up excess articles
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from FeedManager.models import Article, OriginalFeed


class Command(BaseCommand):
    help = "Set max_articles_to_keep for all feeds and optionally clean excess articles"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=500,
            help="New limit for max_articles_to_keep (default: 500)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without making changes",
        )
        parser.add_argument(
            "--clean",
            action="store_true",
            help="Also clean excess articles after updating limits",
        )
        parser.add_argument(
            "--exclude-feeds",
            nargs="+",
            help="Feed IDs to exclude from update",
        )

    def handle(self, *args, **options):
        new_limit = options["limit"]
        dry_run = options["dry_run"]
        clean = options["clean"]
        exclude_ids = options.get("exclude_feeds", [])

        if new_limit < 1:
            self.stdout.write(self.style.ERROR(f"Invalid limit: {new_limit}. Must be at least 1."))
            return

        # Get all feeds
        feeds = OriginalFeed.objects.all()
        if exclude_ids:
            feeds = feeds.exclude(id__in=exclude_ids)

        total_feeds = feeds.count()
        feeds_to_update = feeds.filter(max_articles_to_keep__gt=new_limit).count()

        self.stdout.write("=" * 60)
        self.stdout.write(f"ARTICLE LIMIT UPDATE {'(DRY RUN)' if dry_run else ''}")
        self.stdout.write("=" * 60)
        self.stdout.write(f"Total feeds: {total_feeds}")
        self.stdout.write(f"Feeds to update (currently > {new_limit}): {feeds_to_update}")
        self.stdout.write(f"New limit: {new_limit}")

        if feeds_to_update == 0:
            self.stdout.write(self.style.SUCCESS(f"\n✓ All feeds already have limit ≤ {new_limit}"))
            return

        # Show current distribution
        self.stdout.write("\nCurrent limits distribution:")
        for feed in feeds.order_by("-max_articles_to_keep")[:10]:
            article_count = feed.articles.count()
            excess = max(0, article_count - new_limit)
            status = f" ({excess} excess)" if excess > 0 else ""
            self.stdout.write(
                f"  - {feed.title[:50]}: {feed.max_articles_to_keep} " f"(has {article_count} articles{status})"
            )

        if total_feeds > 10:
            self.stdout.write(f"  ... and {total_feeds - 10} more feeds")

        # Calculate total excess articles
        total_excess = 0
        feeds_with_excess = []
        for feed in feeds:
            article_count = feed.articles.count()
            if article_count > new_limit:
                excess = article_count - new_limit
                total_excess += excess
                feeds_with_excess.append((feed, article_count, excess))

        if total_excess > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"\n⚠️  {total_excess:,} articles exceed the new limit across " f"{len(feeds_with_excess)} feeds"
                )
            )

            if clean:
                self.stdout.write("These articles will be deleted (oldest first)")
            else:
                self.stdout.write("Use --clean to also remove excess articles")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN: No changes made"))
            return

        # Confirm before proceeding
        if not dry_run:
            self.stdout.write("\n" + "=" * 60)
            message = f"Update {feeds_to_update} feeds to limit={new_limit}"
            if clean and total_excess > 0:
                message += f" and DELETE {total_excess:,} articles"

            confirm = input(f"⚠️  {message}? (yes/no): ")
            if confirm.lower() != "yes":
                self.stdout.write(self.style.WARNING("Operation cancelled"))
                return

        # Perform the update
        with transaction.atomic():
            # Update all feed limits
            updated = feeds.filter(max_articles_to_keep__gt=new_limit).update(max_articles_to_keep=new_limit)
            self.stdout.write(self.style.SUCCESS(f"\n✓ Updated {updated} feeds to limit={new_limit}"))

            # Clean excess articles if requested
            if clean and total_excess > 0:
                self.stdout.write("\nCleaning excess articles...")
                total_deleted = 0

                for feed, _article_count, excess in feeds_with_excess:
                    # Get articles to delete (oldest first)
                    articles_to_delete = feed.articles.order_by("published_date")[:excess]
                    deleted_count = articles_to_delete.count()
                    articles_to_delete.delete()

                    total_deleted += deleted_count
                    self.stdout.write(f"  ✓ {feed.title[:40]}: deleted {deleted_count} articles")

                self.stdout.write(self.style.SUCCESS(f"\n✓ Deleted {total_deleted:,} excess articles"))

        # Final summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("OPERATION COMPLETED"))
        self.stdout.write("=" * 60)

        # Show new statistics
        total_articles = Article.objects.count()
        self.stdout.write(f"Total articles remaining: {total_articles:,}")

        # Suggest next steps
        self.stdout.write("\n📝 Next steps:")
        self.stdout.write("  1. Run 'python manage.py optimize_db --vacuum' to reclaim space")
        self.stdout.write("  2. Monitor feed updates to ensure they work correctly")
        self.stdout.write("  3. Consider setting up regular cleanup with clean_old_articles")
