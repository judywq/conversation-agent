import django.db.models.deletion
from django.db import migrations, models
import pgvector.django


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0001_initial"),
        ("conversation", "0018_conversationsession_discussion_context"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversationsession",
            name="discussion_article_ids",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="News article PKs selected as session knowledge base for RAG.",
            ),
        ),
        migrations.CreateModel(
            name="SessionNewsChunk",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("chunk_index", models.PositiveIntegerField(default=0)),
                ("content", models.TextField()),
                (
                    "embedding",
                    pgvector.django.VectorField(blank=True, dimensions=1536, null=True),
                ),
                (
                    "embedding_model",
                    models.CharField(blank=True, default="", max_length=100, null=True),
                ),
                (
                    "embedding_dimensions",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                (
                    "embedding_text_hash",
                    models.CharField(blank=True, default="", max_length=64, null=True),
                ),
                ("embedding_updated_at", models.DateTimeField(blank=True, null=True)),
                (
                    "news_article",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="session_chunks",
                        to="news.newsarticle",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="news_chunks",
                        to="conversation.conversationsession",
                    ),
                ),
            ],
            options={
                "ordering": ("news_article_id", "chunk_index", "id"),
            },
        ),
        migrations.AddIndex(
            model_name="sessionnewschunk",
            index=models.Index(
                fields=["session", "news_article"],
                name="conv_news_chunk_sess_art",
            ),
        ),
        migrations.AddConstraint(
            model_name="sessionnewschunk",
            constraint=models.UniqueConstraint(
                fields=("session", "news_article", "chunk_index"),
                name="unique_session_news_chunk",
            ),
        ),
        migrations.AddIndex(
            model_name="sessionnewschunk",
            index=pgvector.django.HnswIndex(
                ef_construction=64,
                fields=["embedding"],
                m=16,
                name="conv_news_chunk_emb_hnsw",
                opclasses=["vector_cosine_ops"],
            ),
        ),
    ]
