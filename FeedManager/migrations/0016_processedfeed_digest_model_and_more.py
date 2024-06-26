# Generated by Django 5.0.6 on 2024-05-29 20:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('FeedManager', '0015_digest_start_time'),
    ]

    operations = [
        migrations.AddField(
            model_name='processedfeed',
            name='digest_model',
            field=models.CharField(choices=[('gpt-3.5-turbo', 'GPT-3.5 Turbo'), ('gpt-4-turbo', 'GPT-4 Turbo'), ('gpt-4o', 'GPT-4o')], default='gpt-3.5-turbo', help_text='Model for digest generation.', max_length=20),
        ),
        migrations.AddField(
            model_name='processedfeed',
            name='include_content',
            field=models.BooleanField(default=False, help_text='Include full content in digest.'),
        ),
        migrations.AddField(
            model_name='processedfeed',
            name='include_one_line_summary',
            field=models.BooleanField(default=True, help_text='Include one line summary in digest, only works for default summarization.'),
        ),
        migrations.AddField(
            model_name='processedfeed',
            name='include_summary',
            field=models.BooleanField(default=False, help_text='Include full summary in digest.'),
        ),
        migrations.AddField(
            model_name='processedfeed',
            name='use_ai_digest',
            field=models.BooleanField(default=False, help_text='Use AI to process digest content.'),
        ),
    ]
