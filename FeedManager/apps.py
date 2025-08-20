from django.apps import AppConfig
from django.db.backends.signals import connection_created
from django.utils.translation import gettext_lazy as _


def sqlite_optimize_pragmas(sender, connection, **kwargs):
    """
    Set SQLite optimization PRAGMAs on every database connection.
    This ensures optimal performance settings are always active.
    """
    if connection.vendor == "sqlite":
        cursor = connection.cursor()
        # Set optimizations
        cursor.execute("PRAGMA cache_size = -64000;")  # 64MB cache
        cursor.execute("PRAGMA temp_store = MEMORY;")  # Use memory for temp tables
        cursor.execute("PRAGMA journal_mode = WAL;")  # Write-Ahead Logging
        cursor.execute("PRAGMA synchronous = NORMAL;")  # Faster writes
        cursor.execute("PRAGMA mmap_size = 268435456;")  # 256MB memory-mapped I/O
        cursor.close()


class FeedmanagerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "FeedManager"
    verbose_name = _("Feed Manager")

    def ready(self):
        # Connect the optimization function to new database connections
        connection_created.connect(sqlite_optimize_pragmas)
