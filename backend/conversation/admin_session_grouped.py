from __future__ import annotations

from typing import Any

from django.template.response import TemplateResponse

from backend.conversation.models import ConversationSession


class GroupBySessionChangeListMixin:
    """
    Keep the normal model changelist (filters, search, pagination, tabs) but render
    the current page of results grouped under expandable session sections.
    """

    class Media:
        css = {"all": ("conversation/admin_session_tiered.css",)}

    change_list_template = "admin/conversation/group_by_session_change_list.html"
    child_panel_template = ""
    group_panel_id_prefix = "group-for"
    # ChangeList ignores get_queryset().order_by(); set this so rows for one session stay together.
    session_list_ordering: tuple[str, ...] = ()

    def get_ordering(self, request):
        if self.session_list_ordering:
            return list(self.session_list_ordering)
        return super().get_ordering(request)

    def get_session_for_child(self, obj: Any) -> ConversationSession:
        session = getattr(obj, "session", None)
        if session is not None:
            return session
        return obj.turn.session

    def build_session_result_groups(
        self,
        result_list: list[Any],
    ) -> list[tuple[ConversationSession, list[Any]]]:
        groups: list[tuple[ConversationSession, list[Any]]] = []
        current_session: ConversationSession | None = None
        current_children: list[Any] = []

        for obj in result_list:
            session = self.get_session_for_child(obj)
            if current_session is None or session.pk != current_session.pk:
                if current_session is not None:
                    groups.append((current_session, current_children))
                current_session = session
                current_children = [obj]
            else:
                current_children.append(obj)

        if current_session is not None:
            groups.append((current_session, current_children))
        return groups

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        response = super().changelist_view(request, extra_context=extra_context)
        if not isinstance(response, TemplateResponse):
            return response

        cl = response.context_data.get("cl")
        if cl is None:
            return response

        session_result_groups = self.build_session_result_groups(list(cl.result_list))
        response.context_data["session_result_groups"] = session_result_groups
        response.context_data["child_panel_template"] = self.child_panel_template
        response.context_data["group_panel_id_prefix"] = self.group_panel_id_prefix
        return response
