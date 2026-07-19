from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0008_userprofile_proficiency_reference_utterance"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="avatar_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Selected profile avatar preset id (e.g. fox, rabbit, cat).",
                max_length=32,
            ),
        ),
    ]
