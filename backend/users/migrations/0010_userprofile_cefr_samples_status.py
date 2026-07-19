from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0009_userprofile_avatar_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="cefr_samples_generation",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Increments each time CEFR sample generation is started; used to ignore stale jobs.",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="cefr_samples_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("idle", "Idle"),
                    ("pending", "Pending"),
                    ("ready", "Ready"),
                    ("failed", "Failed"),
                ],
                default="idle",
                help_text="Background generation status for CEFR listening samples.",
                max_length=16,
            ),
        ),
    ]
