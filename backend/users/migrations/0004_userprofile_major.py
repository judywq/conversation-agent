from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0003_userprofile_preferred_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="major",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "User's academic major / field of study. Used as the default major for agents "
                    "in their conversation sessions."
                ),
                max_length=120,
            ),
        ),
    ]
