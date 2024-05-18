# Generated by Django 4.2.4 on 2024-05-18 14:26

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='AppSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('auth_code', models.CharField(blank=True, max_length=64, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='OriginalFeed',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.URLField(unique=True)),
                ('title', models.CharField(blank=True, default='', max_length=255)),
                ('max_articles_to_keep', models.PositiveIntegerField(default=1000)),
            ],
        ),
        migrations.CreateModel(
            name='ProcessedFeed',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('update_frequency', models.PositiveIntegerField(default=30)),
                ('max_articles_to_process_per_interval', models.PositiveIntegerField(default=5)),
                ('summary_language', models.CharField(choices=[('en', 'English'), ('zh', 'Chinese'), ('es', 'Spanish'), ('fr', 'French'), ('de', 'German')], default='English', max_length=50)),
                ('additional_prompt', models.TextField(blank=True)),
                ('model', models.CharField(choices=[('gpt-3.5-turbo', 'GPT-3.5 Turbo'), ('gpt-4-turbo', 'GPT-4 Turbo'), ('gpt-4o', 'GPT-4o')], default='gpt-3.5-turbo', max_length=20)),
                ('filter_relational_operator', models.CharField(choices=[('all', 'All'), ('any', 'Any'), ('none', 'None')], default='any', max_length=20)),
                ('feeds', models.ManyToManyField(related_name='processed_feeds', to='FeedManager.originalfeed')),
            ],
        ),
        migrations.CreateModel(
            name='Filter',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('field', models.CharField(choices=[('title', 'Title'), ('content', 'Content'), ('link', 'Link')], max_length=15)),
                ('match_type', models.CharField(choices=[('contains', 'Contains'), ('does_not_contain', 'Does not contain'), ('matches_regex', 'Matches regex'), ('does_not_match_regex', 'Does not match regex'), ('shorter_than', 'Shorter than'), ('longer_than', 'Longer than')], max_length=20)),
                ('value', models.TextField()),
                ('usage', models.CharField(choices=[('feed_filter', 'Feed Filter'), ('summary_filter', 'Summary Filter')], default='feed_filter', max_length=15)),
                ('processed_feed', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='filters', to='FeedManager.processedfeed')),
            ],
        ),
        migrations.CreateModel(
            name='Article',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('url', models.URLField(unique=True)),
                ('published_date', models.DateTimeField()),
                ('content', models.TextField(blank=True, null=True)),
                ('summary', models.TextField(blank=True, null=True)),
                ('summarized', models.BooleanField(default=False)),
                ('original_feed', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='articles', to='FeedManager.originalfeed')),
            ],
        ),
    ]
