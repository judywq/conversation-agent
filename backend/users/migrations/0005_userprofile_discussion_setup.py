from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0004_userprofile_major"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="discussion_category",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Selected news taxonomy category slug for the pending discussion.",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="discussion_subtopic",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Selected news taxonomy subtopic slug for the pending discussion.",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="discussion_scenario",
            field=models.TextField(
                blank=True,
                default="",
                help_text="LLM-generated discussion scenario for the pending conversation.",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="discussion_article_id",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Optional news article id used as scenario context.",
                null=True,
            ),
        ),
    ]
