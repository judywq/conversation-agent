from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("conversation", "0007_agentprofile_display_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversationsession",
            name="speech_act_counters",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
