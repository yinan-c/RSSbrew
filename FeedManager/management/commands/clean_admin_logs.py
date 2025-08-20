"""
Management command to clean old admin log entries
"""

from datetime import datetime, timedelta

from django.contrib.admin.models import LogEntry
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Clean old admin log entries to prevent database bloat"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Keep logs from last N days (default: 90)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )

    def handle(self, *args, **options):
        days_to_keep = options["days"]
        dry_run = options["dry_run"]

        # Calculate cutoff date
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)

        # Find old log entries
        old_logs = LogEntry.objects.filter(action_time__lt=cutoff_date)
        count = old_logs.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS(f"No admin log entries older than {days_to_keep} days found."))
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"DRY RUN: Would delete {count:,} admin log entries older than {cutoff_date.date()}")
            )

            # Show sample of what would be deleted
            sample = old_logs[:5]
            if sample:
                self.stdout.write("\nSample of entries to be deleted:")
                for log in sample:
                    self.stdout.write(f"  - {log.action_time.date()}: {log.user} - {log.object_repr}")
                if count > 5:
                    self.stdout.write(f"  ... and {count - 5} more")
        else:
            # Actually delete the old logs
            deleted_count, _ = old_logs.delete()
            self.stdout.write(
                self.style.SUCCESS(f"✓ Deleted {deleted_count:,} admin log entries older than {cutoff_date.date()}")
            )

            # Report remaining logs
            remaining = LogEntry.objects.count()
            self.stdout.write(f"  Remaining admin log entries: {remaining:,}")
