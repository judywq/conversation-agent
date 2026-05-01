from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("conversation", "0008_conversationsession_speech_act_counters"),
    ]

    operations = [
        migrations.AlterField(
            model_name="conversationsession",
            name="max_turns",
            field=models.IntegerField(default=20),
        ),
    ]

