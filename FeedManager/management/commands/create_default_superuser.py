import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create default superuser'

    def handle(self, *args, **options):
        User = get_user_model()
        if User.objects.count() == 0:
            # Get credentials from environment variables with defaults for development
            username = os.environ.get('ADMIN_USERNAME', 'admin')
            email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
            password = os.environ.get('ADMIN_PASSWORD', 'changeme')

            User.objects.create_superuser(username, email, password)
            self.stdout.write(self.style.SUCCESS(f'Successfully created a new superuser: {username}, please change the password immediately after login.'))

        else:
            self.stdout.write(self.style.SUCCESS(
                'Superuser already exists, but you can change the password by running "python manage.py changepassword admin" command.'))
