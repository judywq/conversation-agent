from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="cefr_sample_choices",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Latest generated CEFR listening samples for the selected topic.",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="cefr_sample_topic",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Topic for which the latest CEFR listening choice was confirmed.",
                max_length=500,
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="profile_completed",
            field=models.BooleanField(
                default=False,
                help_text="Whether the user has completed the required personality profile.",
            ),
        ),
    ]
