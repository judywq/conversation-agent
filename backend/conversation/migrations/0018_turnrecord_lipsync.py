from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("conversation", "0017_turnrecord_utterance_tts"),
    ]

    operations = [
        migrations.AddField(
            model_name="turnrecord",
            name="lipsync",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
