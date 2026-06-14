from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0005_userprofile_discussion_setup"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="discussion_article_ids",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="News article PKs selected for the pending discussion knowledge base.",
            ),
        ),
    ]
