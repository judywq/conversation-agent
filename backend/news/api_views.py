from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import NewsArticle
from .models import NewsClassification
from .taxonomy import TAXONOMY_VERSION
from .taxonomy import get_category
from .taxonomy import get_subtopic
from .taxonomy import serialize_taxonomy


class NewsTaxonomyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"taxonomy_version": TAXONOMY_VERSION, "categories": serialize_taxonomy()})


class ClassifiedArticleListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        category = request.query_params.get("category", "")
        subtopic = request.query_params.get("subtopic", "")
        if not category:
            return Response(
                {"detail": "category is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            get_category(category)
            if subtopic:
                get_subtopic(category, subtopic)
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        classifications = NewsClassification.objects.filter(
            main_category=category,
            status=NewsClassification.Status.SUCCEEDED,
            is_suitable=True,
            article__status=NewsArticle.Status.IMPORTED,
        ).select_related("article")
        if subtopic:
            classifications = classifications.filter(subtopics__contains=[subtopic])
        classifications = classifications.order_by(
            "-article__published_at",
            "-article_id",
        )

        results = [
            serialize_classified_article(classification)
            for classification in classifications[:20]
        ]
        return Response({"results": results})


def serialize_classified_article(classification: NewsClassification) -> dict:
    article = classification.article
    return {
        "id": article.id,
        "title": article.title,
        "summary": article.summary,
        "url": article.url,
        "source_title": article.source_title or article.feed_title,
        "source_url": article.source_url,
        "published_at": article.published_at.isoformat(),
        "main_category": classification.main_category,
        "subtopics": classification.subtopics,
        "cefr_level": classification.cefr_level,
        "confidence": (
            str(classification.confidence)
            if classification.confidence is not None
            else None
        ),
        "rationale": classification.rationale,
    }
