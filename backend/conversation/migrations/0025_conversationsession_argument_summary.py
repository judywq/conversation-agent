from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("conversation", "0024_langmemmemory"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversationsession",
            name="argument_summary",
            field=models.JSONField(
                blank=True,
                help_text="Toulmin-structured argument summary generated when the session ends.",
                null=True,
            ),
        ),
    ]
