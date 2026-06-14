from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("conversation", "0020_rename_knowledgesnippet_exemplar"),
    ]

    operations = [
        migrations.AddField(
            model_name="turnrecord",
            name="lipsync",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
