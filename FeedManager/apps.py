from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FeedmanagerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'FeedManager'
    verbose_name = _('Feed Manager')
