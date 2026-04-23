from django.contrib import admin

from .models import APIKey
from .models import LLMConfig
from .models import LLMModel
from .models import QuotaConfig


@admin.register(QuotaConfig)
class QuotaConfigAdmin(admin.ModelAdmin):
    list_display = ["id", "model", "daily_limit", "created_at", "updated_at"]
    list_display_links = ["model"]
    list_filter = ["model"]


@admin.register(LLMModel)
class LLMModelAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "display_name",
        "name",
        "llm_type",
        "url",
        "order",
        "is_default",
        "is_active",
        "created_at",
        "updated_at",
    ]
    list_display_links = ["display_name"]
    list_filter = ["is_active", "is_default"]
    search_fields = ["name", "display_name"]
    ordering = ["order"]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "display_name",
                    "llm_type",
                    "url",
                ),
            },
        ),
        (
            "Settings",
            {
                "fields": (
                    "order",
                    "is_default",
                    "is_active",
                ),
            },
        ),
    )


@admin.register(LLMConfig)
class LLMConfigAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "purpose",
        "model",
        "get_system_prompt",
        "temperature",
        "is_active",
        "updated_at",
    ]
    list_display_links = ["purpose"]
    list_filter = ["model"]
    actions = ["change_llm_model"]

    @admin.display(description="System Prompt", ordering="system_prompt")
    def get_system_prompt(self, obj):
        return truncatechars(obj.system_prompt, 50)

    @admin.action(description="Change LLM model for selected configs")
    def change_llm_model(self, request, queryset):
        from django import forms
        from django.contrib import messages
        from django.http import HttpResponseRedirect
        from django.template.response import TemplateResponse

        class ModelChangeForm(forms.Form):
            _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
            model = forms.ModelChoiceField(
                queryset=LLMModel.objects.filter(is_active=True),
            )

        # Step 1: Initialize form with selected items
        form = ModelChangeForm(
            request.POST or None,
            initial={"_selected_action": request.POST.getlist("_selected")},
        )

        # Step 2: If this is a POST request with the apply button
        if request.POST and "apply" in request.POST:
            if form.is_valid():
                try:
                    model = form.cleaned_data["model"]
                    count = 0
                    for config in queryset:
                        config.model = model
                        config.save()
                        count += 1
                    msg = (
                        f"Successfully updated {count} configs "
                        f"to use: {model.display_name}"
                    )
                    messages.success(request, msg)
                    return HttpResponseRedirect(request.get_full_path())
                except (ValueError, KeyError) as e:
                    messages.error(request, f"Error updating models: {e!s}")
            else:
                messages.error(request, f"Form validation failed: {form.errors}")

        # Step 3: Show the form
        context = {
            "title": "Change LLM Model",
            "objects": queryset,
            "form": form,
        }
        return TemplateResponse(request, "admin/llm_config_change_model.html", context)


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "name",
        "masked_key",
        "order",
        "is_active",
        "created_at",
        "updated_at",
    ]
    list_display_links = ["name"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    ordering = ["order"]

    @admin.display(
        description="API Key",
    )
    def masked_key(self, obj):
        """Show only the last 4 characters of the key."""
        return f"...{obj.key[-4:]}" if obj.key else ""
