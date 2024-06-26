# Generated by Django 5.0.6 on 2024-05-31 18:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('FeedManager', '0020_rename_url_article_link_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Tag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
            ],
        ),
        migrations.RemoveField(
            model_name='originalfeed',
            name='tag',
        ),
        migrations.AddField(
            model_name='originalfeed',
            name='tags',
            field=models.ManyToManyField(blank=True, help_text='Tags associated with this feed', related_name='original_feeds', to='FeedManager.tag'),
        ),
    ]
