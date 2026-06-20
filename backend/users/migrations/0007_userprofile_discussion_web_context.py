from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0006_userprofile_discussion_article_ids"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="discussion_web_context",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Web search background text for discussion when no news articles are available.",
            ),
        ),
    ]
