from __future__ import annotations

from typing import Any

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def admin_query(context: dict[str, Any], **updates: Any) -> str:
    """
    Build a querystring for Django admin links, preserving current params.

    Usage:
        {% admin_query component__exact='turn_manager' %}
        {% admin_query component__exact=None %}  {# removes param #}
    """
    request = context.get("request")
    if request is None:
        return ""

    query = request.GET.copy()
    for key, value in updates.items():
        if value in (None, ""):
            query.pop(key, None)
        else:
            query[key] = str(value)

    encoded = query.urlencode()
    return f"?{encoded}" if encoded else ""

