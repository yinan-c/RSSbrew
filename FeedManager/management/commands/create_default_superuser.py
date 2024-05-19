from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = 'Create default superuser'

    def handle(self, *args, **options):
        User = get_user_model()
        if User.objects.count() == 0:
            User.objects.create_superuser('admin', 'admin@example.com', 'changeme')
            self.stdout.write(self.style.SUCCESS('Successfully created a new superuser: admin, Password: changeme,  please change it immediately after login.'))

        else:
            self.stdout.write(self.style.SUCCESS(
                'Superuser already exists, but you can change the password by running "python manage.py changepassword admin" command.'))