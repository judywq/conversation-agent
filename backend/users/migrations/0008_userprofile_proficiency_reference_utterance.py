from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0007_userprofile_discussion_web_context"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="proficiency_reference_utterance",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Longest user utterance from a completed session; used to calibrate agent language level.",
            ),
        ),
    ]
