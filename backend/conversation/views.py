from __future__ import annotations

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from backend.conversation.services.discussion_scenario import DISCUSSION_PROFILE_FIELDS
from backend.conversation.services.discussion_scenario import apply_discussion_result_to_profile
from backend.conversation.services.discussion_scenario import generate_discussion_scenario
from backend.news.taxonomy import get_category
from backend.news.taxonomy import get_subtopic
from backend.news.taxonomy import serialize_taxonomy


class DiscussionLoginView(LoginView):
    template_name = "conversation/login.html"
    redirect_authenticated_user = True


class DiscussionSetupView(LoginRequiredMixin, TemplateView):
    template_name = "conversation/discussion_setup.html"
    login_url = reverse_lazy("conversation:discussion-login")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = getattr(self.request.user, "userprofile", None)
        context["taxonomy_json"] = json.dumps(serialize_taxonomy())
        context["selected_category"] = getattr(profile, "discussion_category", "") or ""
        context["selected_subtopic"] = getattr(profile, "discussion_subtopic", "") or ""
        context["scenario"] = getattr(profile, "discussion_scenario", "") or ""
        context["article_title"] = ""
        if profile and profile.discussion_article_id:
            from backend.news.models import NewsArticle

            article = NewsArticle.objects.filter(id=profile.discussion_article_id).first()
            if article:
                context["article_title"] = article.title
        context["conversation_url"] = "/app/conversation"
        return context

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        action = str(request.POST.get("action") or "").strip()
        category = str(request.POST.get("category") or "").strip()
        subtopic = str(request.POST.get("subtopic") or "").strip()
        profile = getattr(request.user, "userprofile", None)
        if profile is None:
            return redirect("conversation:discussion-setup")

        try:
            get_category(category)
            get_subtopic(category, subtopic)
        except ValueError as exc:
            return self.render_to_response(
                self.get_context_data(
                    error=str(exc),
                    selected_category=category,
                    selected_subtopic=subtopic,
                ),
            )

        if action == "generate":
            cefr_level = getattr(profile, "cefr_level", "") or None
            reference_utterance = getattr(profile, "proficiency_reference_utterance", "") or None
            try:
                result = generate_discussion_scenario(
                    category=category,
                    subtopic=subtopic,
                    cefr_level=cefr_level,
                    reference_utterance=reference_utterance,
                )
            except Exception as exc:  # noqa: BLE001
                return self.render_to_response(
                    self.get_context_data(
                        error=f"Could not generate scenario: {exc}",
                        selected_category=category,
                        selected_subtopic=subtopic,
                    ),
                )
            apply_discussion_result_to_profile(profile, result)
            profile.save(update_fields=list(DISCUSSION_PROFILE_FIELDS))
            article_titles = [article.title for article in result.articles if article.title]
            if result.knowledge_source == "web":
                success_message = (
                    "Scenario generated from the subtopic. "
                    "Web background was fetched for discussion retrieval. "
                    "Review the scenario, then continue to the conversation."
                )
            else:
                success_message = (
                    "Scenario generated from "
                    f"{len(result.article_ids)} article(s). "
                    "Article full text was fetched for discussion retrieval. "
                    "Review the scenario, then continue to the conversation."
                )
            return self.render_to_response(
                self.get_context_data(
                    selected_category=category,
                    selected_subtopic=subtopic,
                    scenario=result.scenario,
                    article_title=result.article_title,
                    article_count=len(result.article_ids),
                    article_titles=article_titles,
                    success_message=success_message,
                ),
            )

        if action == "confirm":
            scenario = str(request.POST.get("scenario") or profile.discussion_scenario or "").strip()
            if not scenario:
                return self.render_to_response(
                    self.get_context_data(
                        error="Generate a scenario before continuing.",
                        selected_category=category,
                        selected_subtopic=subtopic,
                    ),
                )
            profile.discussion_category = category
            profile.discussion_subtopic = subtopic
            profile.discussion_scenario = scenario
            profile.save(
                update_fields=[
                    "discussion_category",
                    "discussion_subtopic",
                    "discussion_scenario",
                ],
            )
            return redirect(f"{reverse('conversation:discussion-setup')}?confirmed=1")

        return redirect("conversation:discussion-setup")

    def render_to_response(self, context, **response_kwargs):
        return super().render_to_response(context, **response_kwargs)
