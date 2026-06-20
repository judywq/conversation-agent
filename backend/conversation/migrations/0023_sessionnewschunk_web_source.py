import django.db.models.deletion
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("news", "0002_remove_newsclassification_is_suitable"),
        ("conversation", "0022_alter_exemplar_options"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="sessionnewschunk",
            name="unique_session_news_chunk",
        ),
        migrations.AddField(
            model_name="sessionnewschunk",
            name="source_title",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="sessionnewschunk",
            name="source_uri",
            field=models.CharField(blank=True, default="", max_length=1000),
        ),
        migrations.AlterField(
            model_name="sessionnewschunk",
            name="news_article",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="session_chunks",
                to="news.newsarticle",
            ),
        ),
        migrations.AddConstraint(
            model_name="sessionnewschunk",
            constraint=models.UniqueConstraint(
                condition=models.Q(("news_article__isnull", False)),
                fields=("session", "news_article", "chunk_index"),
                name="unique_session_news_chunk",
            ),
        ),
        migrations.AddConstraint(
            model_name="sessionnewschunk",
            constraint=models.UniqueConstraint(
                condition=models.Q(("news_article__isnull", True)),
                fields=("session", "chunk_index"),
                name="unique_session_web_chunk",
            ),
        ),
    ]
