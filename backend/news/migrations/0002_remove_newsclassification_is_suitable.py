from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("news", "0001_initial"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="newsclassification",
            name="news_class_lookup_idx",
        ),
        migrations.RemoveField(
            model_name="newsclassification",
            name="is_suitable",
        ),
        migrations.AddIndex(
            model_name="newsclassification",
            index=models.Index(
                fields=["taxonomy_version", "main_category", "status"],
                name="news_class_lookup_idx",
            ),
        ),
    ]
