from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Initialize the server by running migrate and create_default_superuser commands.'

    def handle(self, *args, **options):
        # Apply database migrations - essential for ensuring DB schema is up to date
        self.stdout.write('Applying database migrations...')
        call_command('migrate')

        # Create default superuser for initial access
        self.stdout.write('Creating default superuser...')
        call_command('create_default_superuser')
