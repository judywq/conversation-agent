import json

import pandas as pd
from allauth.account.decorators import secure_admin_login
from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import admin as auth_admin
from django.db import transaction
from django.http import HttpRequest
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .forms import AdminUserRegistrationForm
from .forms import UserAdminChangeForm
from .forms import UserAdminCreationForm
from .forms import UserBatchUploadForm
from .models import User
from .models import UserProfile
from backend.users.api.serializers import ALLOWED_AVATAR_IDS

if settings.DJANGO_ADMIN_FORCE_ALLAUTH:
    # Force the `admin` sign in process to go through the `django-allauth` workflow:
    # https://docs.allauth.org/en/latest/common/admin.html#admin
    admin.autodiscover()
    admin.site.login = secure_admin_login(admin.site.login)  # type: ignore[method-assign]


@admin.register(User)
class UserAdmin(auth_admin.UserAdmin):
    form = UserAdminChangeForm
    add_form = UserAdminCreationForm
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("name", "email")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    list_display = [
        "id",
        "username",
        "email",
        "name",
        "is_superuser",
        "is_demo_account",
        "date_joined",
    ]
    search_fields = ["name", "email"]


    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            readonly.append("langmem_memories_preview")
        return readonly

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        if obj is not None:
            fieldsets = [
                *fieldsets,
                (_("LangMem memories"), {"fields": ("langmem_memories_preview",)}),
            ]
        return fieldsets

    @admin.display(description="LangMem memories")
    def langmem_memories_preview(self, obj):
        from backend.conversation.services.speaker_profiles import dump_all_profiles

        try:
            payload = dump_all_profiles(obj)
            rendered = json.dumps(payload, ensure_ascii=False, indent=2)
        except Exception as exc:  # noqa: BLE001
            return str(exc)
        return format_html('<pre style="white-space: pre-wrap;">{}</pre>', rendered)

    @admin.display(
        description="Demo Account",
        boolean=True,
    )
    def is_demo_account(self, obj):
        """Show whether the user is a demo account"""
        if hasattr(obj, "userprofile"):
            return obj.userprofile.is_demo_account
        return False

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Disable the default add user button"""
        return False

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "register/",
                self.admin_site.admin_view(self.register_user_view),
                name="user_register",
            ),
            path(
                "batch-upload/",
                self.admin_site.admin_view(self.batch_upload_view),
                name="user_batch_upload",
            ),
        ]
        return custom_urls + urls

    def register_user_view(self, request):
        if request.method == "POST":
            form = AdminUserRegistrationForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "User registered successfully.")
                return HttpResponseRedirect(reverse("admin:users_user_changelist"))
        else:
            form = AdminUserRegistrationForm()

        context = {
            "form": form,
            "title": "Register New User",
            **self.admin_site.each_context(request),
        }
        return TemplateResponse(request, "admin/users/user/register.html", context)

    def batch_upload_view(self, request):
        if request.method == "POST":
            form = UserBatchUploadForm(request.POST, request.FILES)
            if form.is_valid():
                file = request.FILES["file"]
                must_change_password = form.cleaned_data.get(
                    "must_change_password",
                    True,
                )
                df_data = pd.read_excel(file, keep_default_na=False)
                success_count = 0
                errors = []

                for idx, row in df_data.iterrows():
                    try:
                        with transaction.atomic():
                            row_dict = row.to_dict()
                            user = User.objects.create(
                                email=row_dict["email"],
                                username=row_dict.get("username") or row_dict["email"],
                                name=row_dict.get("name") or "",
                            )
                            user.set_password(str(row_dict["password"]))
                            user.save()

                            # Set must_change_password for batch users
                            if hasattr(user, "userprofile"):
                                user.userprofile.must_change_password = (
                                    must_change_password
                                )
                                user.userprofile.save()

                            # Create verified email address
                            EmailAddress.objects.create(
                                user=user,
                                email=row_dict["email"],
                                primary=True,
                                verified=True,
                            )
                            success_count += 1
                    except (KeyError, ValueError) as e:
                        msg = f"Row {idx + 2}: {e!s}"
                        errors.append(msg)

                if success_count > 0:
                    messages.success(
                        request,
                        f"Successfully created {success_count} users.",
                    )
                if errors:
                    messages.error(request, "Errors occurred: " + "; ".join(errors))
                return HttpResponseRedirect(reverse("admin:users_user_changelist"))
        else:
            form = UserBatchUploadForm()

        context = {
            "form": form,
            "title": "Batch Upload Users",
            **self.admin_site.each_context(request),
        }
        return TemplateResponse(request, "admin/users/user/batch_upload.html", context)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["show_register_button"] = True
        extra_context["show_batch_upload_button"] = True
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "preferred_name",
        "avatar_id",
        "major",
        "must_change_password",
        "is_demo_account",
        "profile_completed",
        "cefr_level",
    ]
    list_filter = ["is_demo_account", "must_change_password", "profile_completed", "cefr_level", "avatar_id"]
    search_fields = ["user__name", "user__email", "preferred_name", "major", "avatar_id"]
    fields = [
        "user",
        "preferred_name",
        "avatar_id",
        "major",
        "must_change_password",
        "is_demo_account",
        "ocean",
        "cefr_level",
        "profile_completed",
        "proficiency_reference_utterance",
        "cefr_sample_topic",
        "cefr_sample_choices",
        "cefr_samples_status",
        "cefr_samples_generation",
    ]

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "avatar_id":
            from django import forms

            choices = [("", "---------")] + [(aid, aid) for aid in sorted(ALLOWED_AVATAR_IDS)]
            return forms.ChoiceField(
                choices=choices,
                required=False,
                label=db_field.verbose_name,
                help_text=db_field.help_text,
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)
