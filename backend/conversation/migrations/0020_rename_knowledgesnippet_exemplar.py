from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("conversation", "0019_session_news_knowledge"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="KnowledgeSnippet",
            new_name="Exemplar",
        ),
    ]
