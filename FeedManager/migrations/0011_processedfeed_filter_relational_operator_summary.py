# Generated by Django 5.0.6 on 2024-05-28 17:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('FeedManager', '0010_processedfeed_additional_prompt_for_digest_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='processedfeed',
            name='filter_relational_operator_summary',
            field=models.CharField(choices=[('all', 'All'), ('any', 'Any'), ('none', 'None')], default='any', help_text='The included articles must match All/Any/None of the filters for summarization.', max_length=20),
        ),
    ]
