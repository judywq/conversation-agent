from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0001_initial"),
        ("conversation", "0017_turnrecord_utterance_tts"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversationsession",
            name="news_category",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="conversationsession",
            name="news_subtopic",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="conversationsession",
            name="scenario",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="conversationsession",
            name="news_article",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="conversation_sessions",
                to="news.newsarticle",
            ),
        ),
    ]
