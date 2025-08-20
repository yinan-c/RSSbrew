"""
Management command to optimize database performance with automatic backup
"""

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import cast

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Optimize database performance (indexes, vacuum, analyze) with automatic backup"

    def add_arguments(self, parser):
        parser.add_argument(
            "--vacuum",
            action="store_true",
            help="Run VACUUM to reclaim space (SQLite only)",
        )
        parser.add_argument(
            "--analyze",
            action="store_true",
            help="Run ANALYZE to update statistics",
        )
        parser.add_argument(
            "--pragma",
            action="store_true",
            help="Set optimal SQLite pragmas",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Run all optimizations",
        )
        parser.add_argument(
            "--no-backup",
            action="store_true",
            help="Skip automatic backup (not recommended)",
        )

    def create_backup(self, db_path):
        """Create a timestamped backup of the database"""
        if not os.path.exists(db_path):
            return None

        # Create backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{db_path}.backup_{timestamp}"

        # Check if we have enough space for backup
        db_size = os.path.getsize(db_path)
        stat = os.statvfs(os.path.dirname(db_path))
        free_space = stat.f_bavail * stat.f_frsize

        if free_space < db_size * 1.5:  # Need at least 1.5x the DB size
            self.stdout.write(
                self.style.WARNING(
                    f"Warning: Low disk space. Need {db_size * 1.5 / (1024**2):.1f}MB, "
                    f"have {free_space / (1024**2):.1f}MB free"
                )
            )
            return None

        # Create the backup
        self.stdout.write(f"Creating backup: {backup_path}")
        try:
            shutil.copy2(db_path, backup_path)
            backup_size = os.path.getsize(backup_path) / (1024 * 1024)  # MB
            self.stdout.write(self.style.SUCCESS(f"✓ Backup created: {backup_path} ({backup_size:.1f}MB)"))

            # Clean up old backups (keep only last 3)
            self.cleanup_old_backups(db_path)

            return backup_path
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to create backup: {e}"))
            return None

    def cleanup_old_backups(self, db_path):
        """Keep only the 3 most recent backups"""
        backup_dir = os.path.dirname(db_path)
        backup_prefix = os.path.basename(db_path) + ".backup_"

        # Find all backup files
        backups = []
        for file in os.listdir(backup_dir):
            if file.startswith(backup_prefix):
                full_path = os.path.join(backup_dir, file)
                backups.append((full_path, os.path.getmtime(full_path)))

        # Sort by modification time (newest first)
        backups.sort(key=lambda x: x[1], reverse=True)

        # Remove old backups (keep only 3)
        for backup_path, _ in backups[3:]:
            try:
                os.remove(backup_path)
                self.stdout.write(f"  Removed old backup: {os.path.basename(backup_path)}")
            except Exception as e:
                self.stdout.write(f"  Could not remove old backup: {e}")

    def handle(self, *args, **options):
        db_engine = cast(str, settings.DATABASES["default"]["ENGINE"])
        is_sqlite = "sqlite" in db_engine

        if not is_sqlite and (options["vacuum"] or options["pragma"]):
            self.stdout.write(
                self.style.WARNING("Note: VACUUM and PRAGMA operations are SQLite-specific and will be skipped.")
            )

        if options["all"]:
            options["vacuum"] = True
            options["analyze"] = True
            options["pragma"] = True

        # Create backup for SQLite before optimization (unless --no-backup is specified)
        backup_path = None
        if is_sqlite and not options["no_backup"]:
            db_path = cast(Path, settings.DATABASES["default"]["NAME"])
            self.stdout.write("\n" + "=" * 50)
            self.stdout.write("STEP 1: Creating database backup")
            self.stdout.write("=" * 50)
            backup_path = self.create_backup(db_path)
            if not backup_path and options["vacuum"]:
                # If backup failed and we're doing vacuum, ask for confirmation
                confirm = input("\n⚠️  No backup created. Continue with optimization? (yes/no): ")
                if confirm.lower() != "yes":
                    self.stdout.write(self.style.WARNING("Optimization cancelled."))
                    return

        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("STEP 2: Running database optimizations")
        self.stdout.write("=" * 50 + "\n")

        success = True

        try:
            with connection.cursor() as cursor:
                # Set optimal SQLite pragmas
                if options["pragma"] and is_sqlite:
                    self.stdout.write("Setting optimal SQLite pragmas...")

                    # Increase cache size to 64MB
                    cursor.execute("PRAGMA cache_size = -64000")
                    self.stdout.write("  ✓ Cache size set to 64MB")

                    # Use Write-Ahead Logging for better concurrency
                    cursor.execute("PRAGMA journal_mode = WAL")
                    self.stdout.write("  ✓ WAL mode enabled")

                    # Optimize for faster writes
                    cursor.execute("PRAGMA synchronous = NORMAL")
                    self.stdout.write("  ✓ Synchronous mode set to NORMAL")

                    # Enable automatic indexing
                    cursor.execute("PRAGMA automatic_index = ON")
                    self.stdout.write("  ✓ Automatic indexing enabled")

                    # Increase temp store memory
                    cursor.execute("PRAGMA temp_store = MEMORY")
                    self.stdout.write("  ✓ Temp store set to memory")

                    self.stdout.write(self.style.SUCCESS("SQLite pragmas optimized\n"))

                # Run ANALYZE to update statistics
                if options["analyze"]:
                    self.stdout.write("Running ANALYZE to update statistics...")
                    if is_sqlite:
                        cursor.execute("ANALYZE")
                    else:
                        cursor.execute("ANALYZE;")
                    self.stdout.write(self.style.SUCCESS("✓ Statistics updated\n"))

                # Run VACUUM (SQLite only)
                if options["vacuum"] and is_sqlite:
                    self.stdout.write("Running VACUUM to reclaim space (this may take a while)...")
                    # Get current database size
                    db_path = cast(Path, settings.DATABASES["default"]["NAME"])
                    if os.path.exists(db_path):
                        size_before = os.path.getsize(db_path) / (1024 * 1024)  # MB

                        cursor.execute("VACUUM")

                        size_after = os.path.getsize(db_path) / (1024 * 1024)  # MB
                        saved = size_before - size_after

                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✓ VACUUM completed. Size: {size_before:.1f}MB → {size_after:.1f}MB "
                                f"(saved {saved:.1f}MB)\n"
                            )
                        )

                # Run optimizer
                if is_sqlite:
                    cursor.execute("PRAGMA optimize")
                    self.stdout.write(self.style.SUCCESS("✓ Query optimizer updated\n"))

                # Check and report on indexes
                if is_sqlite:
                    cursor.execute("""
                        SELECT name, tbl_name
                        FROM sqlite_master
                        WHERE type='index'
                        AND name LIKE '%_idx'
                        ORDER BY tbl_name
                    """)
                    custom_indexes = cursor.fetchall()
                    if custom_indexes:
                        self.stdout.write("Performance indexes found:")
                        for idx_name, table_name in custom_indexes:
                            self.stdout.write(f"  ✓ {idx_name} on {table_name}")
                        self.stdout.write("")

        except Exception as e:
            success = False
            self.stdout.write(self.style.ERROR(f"\n❌ Optimization failed: {e}"))

            if backup_path:
                self.stdout.write(
                    self.style.WARNING(f"\nTo restore from backup, run:\n" f"  cp {backup_path} {db_path}")
                )

        if success:
            self.stdout.write("\n" + "=" * 50)
            self.stdout.write(self.style.SUCCESS("✓ Database optimization completed successfully!"))
            self.stdout.write("=" * 50)

            if backup_path:
                self.stdout.write(
                    f"\nBackup retained at: {backup_path}\n"
                    f"You can delete it after verifying the app works correctly:\n"
                    f"  rm {backup_path}"
                )

            self.stdout.write(
                self.style.SUCCESS("\n✅ You can now restart Docker safely:\n" "  docker-compose restart rssbrew")
            )
