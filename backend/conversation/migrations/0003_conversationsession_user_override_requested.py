from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("conversation", "0002_conversationsession_paused"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversationsession",
            name="user_override_requested",
            field=models.BooleanField(default=False),
        ),
    ]

