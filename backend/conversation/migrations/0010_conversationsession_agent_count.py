from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("conversation", "0009_conversationsession_max_turns_default_20"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversationsession",
            name="agent_count",
            field=models.IntegerField(default=3),
        ),
    ]

