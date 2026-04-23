from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("llm_caller", "0022_vocabularyquizsubmission_and_more"),
    ]

    operations = [
        migrations.DeleteModel(name="VocabularyQuizSubmissionItem"),
        migrations.DeleteModel(name="VocabularyQuizSubmission"),
        migrations.DeleteModel(name="TextExplanation"),
        migrations.DeleteModel(name="StoryOption"),
        migrations.DeleteModel(name="StoryProgress"),
        migrations.DeleteModel(name="StorySkeleton"),
        migrations.DeleteModel(name="GameScenario"),
        migrations.DeleteModel(name="GameStory"),
    ]

