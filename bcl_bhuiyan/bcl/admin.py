
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import models
from django.forms.models import BaseInlineFormSet
from django import forms

from .models import (
    IELTSMockTest,
    ExamModule,
    ExamSection,
    Question,
    QuestionOption,
    CandidateAttempt,
    CandidateAnswer,
    WritingEvaluation,
)


# ==========================================
# IELTS MOCK TEST ADMIN CONFIGURATION
# ==========================================

admin.site.site_header = "IELTS Mock Test Administration"
admin.site.site_title = "IELTS Admin"
admin.site.index_title = "IELTS Management Dashboard"


# ==========================================
# 1. EXAM MODULE INLINE
# ==========================================

class ExamModuleInline(admin.TabularInline):
    model = ExamModule
    extra = 0

    fields = (
        "module_type",
        "duration_minutes",
        "is_active",
    )


class ExamSectionInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        used_orders = set(
            self.queryset.values_list("order", flat=True)
        )
        next_order = max(used_orders, default=0) + 1
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or not form.cleaned_data:
                continue
            if form.cleaned_data.get("DELETE"):
                continue
            instance = form.instance
            if instance._state.adding and instance.order in used_orders:
                instance.order = next_order
                form.cleaned_data["order"] = next_order
                used_orders.add(next_order)
                next_order += 1
            else:
                used_orders.add(instance.order)


class ExamSectionInline(admin.StackedInline):
    model = ExamSection
    formset = ExamSectionInlineFormSet
    extra = 1
    fields = (
        "order",
        "title",
        "instructions",
        "passage_instructions",
        "passage",
        "audio_file",
        "image",
    )


class ExamSectionAdminForm(forms.ModelForm):
    class Meta:
        model = ExamSection
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["instructions"].label = "Question instructions"
        self.fields["instructions"].help_text = (
            "Instructions shown above the questions on the right side."
        )
        self.fields["passage_instructions"].label = "Passage instructions"

    def clean_order(self):
        order = self.cleaned_data["order"]
        module = self.cleaned_data.get("module")
        if (
            module
            and self.instance._state.adding
            and ExamSection.objects.filter(module=module, order=order).exists()
        ):
            return (
                ExamSection.objects.filter(module=module)
                .order_by("-order")
                .values_list("order", flat=True)
                .first()
                + 1
            )
        return order


ExamSectionInline.form = ExamSectionAdminForm


class QuestionInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        used_orders = set(self.queryset.values_list("order", flat=True))
        next_order = max(used_orders, default=0) + 1
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or not form.cleaned_data:
                continue
            if form.cleaned_data.get("DELETE"):
                continue
            instance = form.instance
            if instance._state.adding and instance.order in used_orders:
                instance.order = next_order
                form.cleaned_data["order"] = next_order
                used_orders.add(next_order)
                next_order += 1
            else:
                used_orders.add(instance.order)


class QuestionInline(admin.StackedInline):
    model = Question
    formset = QuestionInlineFormSet
    extra = 1
    fields = (
        "order",
        "question_type",
        "question_text",
        "question_instructions",
        "answer_count",
        "marks",
        "correct_answer",
        "explanation",
    )


# ==========================================
# 2. IELTS MOCK TEST ADMIN
# ==========================================

@admin.register(IELTSMockTest)
class IELTSMockTestAdmin(admin.ModelAdmin):

    list_display = (
        "test_number",
        "title",
        "is_published",
        "created_at",
    )

    list_filter = (
        "is_published",
        "created_at",
    )

    search_fields = (
        "title",
        "description",
    )

    ordering = ("test_number",)

    list_editable = ("is_published",)

    inlines = [ExamModuleInline]


# ==========================================
# 3. EXAM MODULE ADMIN
# ==========================================

@admin.register(ExamModule)
class ExamModuleAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "mock_test",
        "module_type",
        "duration_minutes",
        "is_active",
    )

    list_filter = (
        "module_type",
        "is_active",
    )

    search_fields = (
        "mock_test__title",
    )

    list_select_related = ("mock_test",)
    inlines = [ExamSectionInline]


# ==========================================
# 4. EXAM SECTION ADMIN
# ==========================================

@admin.register(ExamSection)
class ExamSectionAdmin(admin.ModelAdmin):
    form = ExamSectionAdminForm

    list_display = (
        "id",
        "title",
        "module",
        "order",
    )

    list_filter = (
        "module__module_type",
    )

    search_fields = (
        "title",
        "module__mock_test__title",
    )

    list_select_related = (
        "module",
        "module__mock_test",
    )
    inlines = [QuestionInline]


# ==========================================
# 5. QUESTION OPTION INLINE
# ==========================================

class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 4

    fields = (
        "option_key",
        "option_text",
        "is_correct",
        "order",
    )
    verbose_name = "Option (use A, B, C… as the option key)"
    verbose_name_plural = "Options (add the choices used by MCQ or Matching questions)"
    formfield_overrides = {
        models.CharField: {"widget": forms.TextInput(attrs={"placeholder": "Optional"})},
    }


# ==========================================
# 6. QUESTION ADMIN
# ==========================================

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "short_question",
        "question_type",
        "answer_count",
        "section",
        "order",
        "marks",
    )

    list_filter = (
        "question_type",
        "section__module__module_type",
    )

    search_fields = (
        "question_text",
        "question_instructions",
        "section__title",
    )

    list_select_related = (
        "section",
        "section__module",
    )

    inlines = [QuestionOptionInline]
    fieldsets = (
        (
            "Question",
            {
                "fields": (
                    "section",
                    "order",
                    "question_type",
                    "question_text",
                    "question_instructions",
                    "answer_count",
                    "marks",
                )
            },
        ),
        (
            "Answer key",
            {
                "fields": ("correct_answer", "explanation"),
                "description": (
                    "For Multiple Choice, Matching, and Matching Information, "
                    "add A/B/C options in the Options section below and mark the "
                    "correct option. For fill-in-the-blank, separate answers with ;;;."
                ),
            },
        ),
    )

    @admin.display(description="Question")
    def short_question(self, obj):
        return obj.question_text[:80]


# ==========================================
# 7. QUESTION OPTION ADMIN
# ==========================================

@admin.register(QuestionOption)
class QuestionOptionAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "question",
        "option_key",
        "option_text",
        "is_correct",
        "order",
    )

    list_filter = ("is_correct",)

    search_fields = (
        "option_text",
        "question__question_text",
    )

    list_select_related = ("question",)


# ==========================================
# 8. CANDIDATE ATTEMPT ADMIN
# ==========================================

@admin.register(CandidateAttempt)
class CandidateAttemptAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "candidate",
        "module",
        "status",
        "started_at",
        "raw_score",
        "band_score",
        "violation_count",
    )

    list_filter = (
        "status",
        "module__module_type",
        "started_at",
    )

    search_fields = (
        "candidate__username",
        "candidate__email",
        "module__mock_test__title",
    )

    readonly_fields = (
        "candidate",
        "module",
        "status",
        "started_at",
        "expires_at",
        "submitted_at",
        "violation_count",
        "raw_score",
        "band_score",
    )

    list_select_related = (
        "candidate",
        "module",
        "module__mock_test",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ==========================================
# 9. CANDIDATE ANSWER ADMIN
# ==========================================

@admin.register(CandidateAnswer)
class CandidateAnswerAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "attempt",
        "question",
        "is_flagged",
        "is_correct",
        "awarded_marks",
        "saved_at",
    )

    list_filter = (
        "is_flagged",
        "is_correct",
    )

    search_fields = (
        "attempt__candidate__username",
        "question__question_text",
    )

    readonly_fields = (
        "attempt",
        "question",
        "answer_text",
        "is_flagged",
        "is_correct",
        "awarded_marks",
        "saved_at",
    )

    list_select_related = (
        "attempt",
        "attempt__candidate",
        "question",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ==========================================
# 10. WRITING EVALUATION ADMIN
# ==========================================

@admin.register(WritingEvaluation)
class WritingEvaluationAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "attempt",
        "examiner",
        "task_achievement",
        "coherence_cohesion",
        "lexical_resource",
        "grammatical_range_accuracy",
        "evaluated_at",
    )

    list_filter = (
        "evaluated_at",
    )

    search_fields = (
        "attempt__candidate__username",
        "examiner__username",
    )

    readonly_fields = ("evaluated_at",)

    list_select_related = (
        "attempt",
        "attempt__candidate",
        "examiner",
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.examiner = request.user
        obj.full_clean()
        super().save_model(request, obj, form, change)

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))

        if obj is None:
            fields.append("examiner")
        else:
            fields.append("attempt")
            fields.append("examiner")

        return fields
