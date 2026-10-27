from decimal import Decimal
from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Count, Q
from django.forms.models import BaseInlineFormSet
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import (
    IELTSMockTest,
    ExamModule,
    ExamSection,
    Question,
    QuestionOption,
    CandidateAttempt,
    CandidateAnswer,
    WritingEvaluation,
    FullMockAttempt,
)


# ==============================================================================
# ADMIN SITE BRANDING
# ==============================================================================

admin.site.site_header = "IELTS Bhuiyan — Exam Portal Administration"
admin.site.site_title = "IELTS Bhuiyan Admin"
admin.site.index_title = "Exam Management & Question Setting Dashboard"


# ==============================================================================
# BASE MODEL ADMIN (SHARED ASSETS)
# ==============================================================================

class QuestionSetterBaseAdmin(admin.ModelAdmin):
    """Base Admin providing ergonomic CSS for badges, textareas, and guidance cards."""
    class Media:
        css = {
            "all": ("css/admin_question_setter.css",)
        }


# ==============================================================================
# 1. FORMS & FORMSETS
# ==============================================================================

class IELTSMockTestAdminForm(forms.ModelForm):
    class Meta:
        model = IELTSMockTest
        fields = "__all__"
        widgets = {
            "title": forms.TextInput(attrs={
                "placeholder": "e.g. Cambridge IELTS 18 - Academic Test 1",
                "style": "width: 100%; max-width: 600px;",
            }),
            "description": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Optional summary or operational notes about this mock test.",
                "style": "width: 100%; max-width: 800px; box-sizing: border-box;",
            }),
        }


class ExamModuleAdminForm(forms.ModelForm):
    class Meta:
        model = ExamModule
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "audio_file" in self.fields:
            self.fields["audio_file"].help_text = (
                "Continuous master audio for the entire Listening module (covers Parts 1–4 and all questions). "
                "If uploaded, this single file plays continuously across all parts. "
                "If left empty, you can upload individual audio files for each section/part below."
            )
        if "duration_minutes" in self.fields:
            self.fields["duration_minutes"].help_text = (
                "Standard module durations: Reading = 60 min, Listening = 30 min (or 40 min), Writing = 60 min."
            )


class ExamSectionInlineFormSet(BaseInlineFormSet):
    """Ensure automated sequential ordering when adding multiple sections."""
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


class ExamSectionAdminForm(forms.ModelForm):
    class Meta:
        model = ExamSection
        fields = "__all__"
        widgets = {
            "title": forms.TextInput(attrs={
                "placeholder": "e.g. Passage 1: The Secret Life of Bees  OR  Part 1: Accommodation Inquiry",
                "style": "width: 100%; max-width: 650px;",
            }),
            "passage": forms.Textarea(attrs={
                "rows": 16,
                "class": "passage-textarea",
                "placeholder": "Paste or write the full reading passage, text, or essay prompt here...",
            }),
            "passage_instructions": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": 'Introductory text shown directly above the passage (e.g. "You should spend about 20 minutes on Questions 1–13...")',
                "style": "width: 100%; max-width: 850px; box-sizing: border-box;",
            }),
            "instructions": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": 'Instructions shown above the questions panel on the right (e.g. "Questions 1–6: Choose the correct letter, A, B, C or D.")',
                "style": "width: 100%; max-width: 850px; box-sizing: border-box;",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["instructions"].label = "Question Pane Instructions"
        self.fields["instructions"].help_text = "Instructions shown above the question items in the right-hand panel."
        self.fields["passage_instructions"].label = "Passage Header Note"
        if "audio_file" in self.fields:
            self.fields["audio_file"].help_text = (
                "Individual audio for this specific part/section. "
                "Only used if the parent module does not have a continuous master audio file."
            )

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


class QuestionInlineFormSet(BaseInlineFormSet):
    """Ensure automated sequential ordering when adding multiple questions."""
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


class QuestionAdminForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = "__all__"
        widgets = {
            "question_text": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": (
                    "Enter the question text or prompt statement.\n"
                    "★ FOR FILL-IN-THE-BLANKS: Type three underscores (___) where candidate types their answer.\n"
                    "Example: The conference registration fee is ___ dollars."
                ),
                "style": "width: 100%; max-width: 850px; font-size: 13.5px; box-sizing: border-box;",
            }),
            "question_instructions": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": (
                    "Optional instructions shown directly above this question group.\n"
                    "Example: Questions 1–5: Complete the notes below. Write NO MORE THAN TWO WORDS AND/OR A NUMBER."
                ),
                "style": "width: 100%; max-width: 850px; box-sizing: border-box;",
            }),
            "correct_answer": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": (
                    "Canonical correct answer key(s).\n"
                    "• Fill in the blanks: ans1 / alt1 ;;; ans2 / alt2\n"
                    "• Multiple Choice: A (or B, C, D)\n"
                    "• Multi-Select: A, C\n"
                    "• True/False/Not Given: TRUE or FALSE or NOT GIVEN\n"
                    "• Writing Task: Leave blank (evaluated manually)"
                ),
                "style": "width: 100%; max-width: 850px; font-family: Consolas, monospace; font-size: 13px; box-sizing: border-box;",
            }),
            "table_content": forms.Textarea(attrs={
                "rows": 5,
                "placeholder": "Optional HTML or Markdown table for structured question tables.",
                "style": "width: 100%; max-width: 850px; font-family: monospace; font-size: 12.5px; box-sizing: border-box;",
            }),
            "explanation": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": (
                    "Explanation shown to candidates on their test result page.\n"
                    "• Single question: Enter the explanation text.\n"
                    "• Multiple blanks in one question: Wrap each blank's explanation in double quotes \"...\" \"...\" or separate with ;;; or prefix with Q{num} headers (e.g. Q23: ... Q24: ...)."
                ),
                "style": "width: 100%; max-width: 850px; box-sizing: border-box;",
            }),
            "passage_excerpt": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Exact passage excerpt/sentence to highlight in the passage on review.",
                "style": "width: 100%; max-width: 850px; box-sizing: border-box;",
            }),
            "what_question_asks": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Key requirements or keywords of what the question asks.",
                "style": "width: 100%; max-width: 850px; box-sizing: border-box;",
            }),
            "what_passage_says": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "What the passage states related to this question.",
                "style": "width: 100%; max-width: 850px; box-sizing: border-box;",
            }),
            "why_answer": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Detailed justification of why this answer is correct.",
                "style": "width: 100%; max-width: 850px; box-sizing: border-box;",
            }),
            "paraphrase": forms.Textarea(attrs={
                "rows": 2,
                "placeholder": "e.g. question: 'unique to the island' -> passage: 'six are found only there'",
                "style": "width: 100%; max-width: 850px; font-family: monospace; box-sizing: border-box;",
            }),
            "tip": forms.Textarea(attrs={
                "rows": 2,
                "placeholder": "Exam tip or trap warning for this question.",
                "style": "width: 100%; max-width: 850px; box-sizing: border-box;",
            }),
        }


# Question types that use selectable options (MCQ, matching, multi-select)
MCQ_OPTION_TYPES = (
    Question.QuestionType.MCQ,
    Question.QuestionType.MATCHING,
    Question.QuestionType.MATCHING_INFORMATION,
    Question.QuestionType.MULTI_SELECT,
    Question.QuestionType.TRUE_FALSE_NOT_GIVEN,
    Question.QuestionType.YES_NO_NOT_GIVEN,
)


# ==============================================================================
# 2. INLINES
# ==============================================================================

class ExamModuleInline(admin.TabularInline):
    model = ExamModule
    extra = 0
    show_change_link = True
    fields = (
        "module_type",
        "duration_minutes",
        "audio_file",
        "sections_summary",
        "is_active",
    )
    readonly_fields = ("sections_summary",)

    @admin.display(description="Sections & Content")
    def sections_summary(self, obj):
        if not obj.pk:
            return "Save first"
        s_count = obj.sections.count()
        q_count = sum(s.questions.count() for s in obj.sections.all())
        url = reverse("admin:bcl_examsection_changelist") + f"?module__id__exact={obj.pk}"
        return format_html(
            '<a class="admin-action-link" href="{}">{} sections ({} Qs) ➔</a>',
            url,
            s_count,
            q_count,
        )


class ExamSectionInline(admin.StackedInline):
    model = ExamSection
    form = ExamSectionAdminForm
    formset = ExamSectionInlineFormSet
    extra = 0
    show_change_link = True
    classes = ("collapse",)
    fields = (
        "order",
        "title",
        "instructions",
        "passage_instructions",
        "passage",
        "audio_file",
        "image",
    )


class QuestionOptionInlineForQuestion(admin.TabularInline):
    """Options inline used inside the standalone Question admin page."""
    model = QuestionOption
    extra = 4
    fields = ("order", "option_key", "option_text", "is_correct")
    verbose_name = "Option / Choice"
    verbose_name_plural = "⬇ Options / Choices  (MCQ · Matching · Multi-Select · TFNG · YNNG)"
    formfield_overrides = {
        models.CharField: {"widget": forms.TextInput(attrs={"size": "6"})},
    }

    def get_extra(self, request, obj=None, **kwargs):
        """Pre-populate 4 rows for new MCQ questions; 0 for existing that already have options."""
        if obj and obj.pk and obj.options.exists():
            return 1
        return 4


# Pre-built A/B/C/D option form for MCQ questions created from ExamSection inline
class MCQOptionInlineForSection(admin.TabularInline):
    """Lightweight options inline shown when editing a Question directly (not nested)."""
    model = QuestionOption
    extra = 4
    max_num = 8
    fields = ("order", "option_key", "option_text", "is_correct")
    verbose_name = "MCQ Option"
    verbose_name_plural = "⬇ MCQ / Matching Options  — fill in A, B, C, D and tick the correct one"
    formfield_overrides = {
        models.CharField: {"widget": forms.TextInput(attrs={"size": "6"})},
    }


# Keep old name as alias so nothing else breaks
QuestionOptionInline = QuestionOptionInlineForQuestion


class QuestionInline(admin.StackedInline):
    model = Question
    form = QuestionAdminForm
    formset = QuestionInlineFormSet
    extra = 0
    show_change_link = True  # ← Click "Change" to open the full Question page with MCQ options
    classes = ("collapse",)
    fields = (
        "order",
        "question_type",
        "question_text",
        "question_instructions",
        "answer_count",
        "marks",
        "correct_answer",
        "explanation",
        "image",
        "table_content",
        "options_preview",
    )
    readonly_fields = ("options_preview",)

    @admin.display(description="MCQ Options (current)")
    def options_preview(self, obj):
        """Show existing MCQ options inline so setter can verify without leaving ExamSection."""
        if not obj or not obj.pk:
            return format_html(
                '<span style="color:#64748b;font-size:12px;">'
                "Save question first, then click <b>Change ↗</b> above to add MCQ options."
                "</span>"
            )
        if obj.question_type not in MCQ_OPTION_TYPES:
            return format_html(
                '<span style="color:#64748b;font-size:12px;">'
                "No options needed for {} questions."
                "</span>",
                obj.get_question_type_display(),
            )
        opts = list(obj.options.order_by("order", "option_key"))
        if not opts:
            url = reverse("admin:bcl_question_change", args=[obj.pk])
            return format_html(
                '<span style="color:#dc2626;font-weight:600;">'
                "⚠ No options added yet — "
                '<a href="{}" target="_blank">click here to add A / B / C / D options ↗</a>'
                "</span>",
                url,
            )
        rows = []
        for o in opts:
            badge_color = "#16a34a" if o.is_correct else "#64748b"
            tick = " ✓" if o.is_correct else ""
            rows.append(
                format_html(
                    '<span style="display:inline-block;margin:2px 6px 2px 0;padding:2px 10px;'
                    'border-radius:4px;background:#f1f5f9;border:1px solid #e2e8f0;'
                    'font-size:12.5px;color:{};font-weight:600;">'
                    "{}: {}{}"
                    "</span>",
                    badge_color,
                    o.option_key,
                    o.option_text or "(no text)",
                    tick,
                )
            )
        url = reverse("admin:bcl_question_change", args=[obj.pk])
        rows.append(
            format_html(
                ' &nbsp;<a href="{}" target="_blank" style="font-size:11px;color:#3b82f6;">'
                "Edit options ↗</a>",
                url,
            )
        )
        return mark_safe("".join(str(r) for r in rows))


# ==============================================================================
# 3. IELTS MOCK TEST ADMIN
# ==============================================================================

@admin.register(IELTSMockTest)
class IELTSMockTestAdmin(QuestionSetterBaseAdmin):
    form = IELTSMockTestAdminForm

    list_display = (
        "test_number",
        "title",
        "modules_overview",
        "total_questions_count",
        "is_published",
        "created_at",
    )
    list_display_links = ("test_number", "title")
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

    fieldsets = (
        (
            "Mock Test Identification",
            {
                "fields": (
                    "test_number",
                    "title",
                    "is_published",
                ),
                "description": "General identification for the full IELTS test.",
            },
        ),
        (
            "Overview & Description",
            {
                "fields": ("description",),
                "description": "Optional administrative summary or candidate-facing description.",
            },
        ),
    )

    @admin.display(description="Modules Status")
    def modules_overview(self, obj):
        modules = list(obj.modules.all())
        if not modules:
            return format_html('<span class="admin-badge badge-draft">No modules</span>')
        badges = []
        for m in sorted(modules, key=lambda x: {"reading": 1, "listening": 2, "writing": 3}.get(x.module_type, 99)):
            m_type = m.get_module_type_display()
            sec_count = m.sections.count()
            css_class = f"badge-{m.module_type}"
            change_url = reverse("admin:bcl_exammodule_change", args=[m.pk])
            badges.append(
                format_html(
                    '<a href="{}" title="Edit {} Module" style="text-decoration:none;">'
                    '<span class="admin-badge {}">{} ({} parts)</span></a>',
                    change_url,
                    m_type,
                    css_class,
                    m_type,
                    sec_count,
                )
            )
        return mark_safe(" ".join(badges))

    @admin.display(description="Total Questions")
    def total_questions_count(self, obj):
        count = Question.objects.filter(section__module__mock_test=obj).count()
        return format_html("<b>{}</b> Qs", count)

    @admin.display(description="Publication")
    def status_badge(self, obj):
        if obj.is_published:
            return format_html('<span class="admin-badge badge-published">● Published</span>')
        return format_html('<span class="admin-badge badge-draft">○ Draft</span>')


# ==============================================================================
# 4. EXAM MODULE ADMIN
# ==============================================================================

@admin.register(ExamModule)
class ExamModuleAdmin(QuestionSetterBaseAdmin):
    form = ExamModuleAdminForm

    list_display = (
        "id",
        "mock_test_link",
        "module_type_badge",
        "duration_minutes",
        "sections_link",
        "audio_status",
        "is_active",
    )
    list_display_links = ("id", "module_type_badge")
    list_filter = (
        "mock_test",
        "module_type",
        "is_active",
    )
    search_fields = (
        "mock_test__title",
        "instructions",
        "module_type",
    )
    autocomplete_fields = ["mock_test"]
    list_select_related = ("mock_test",)
    inlines = [ExamSectionInline]

    fieldsets = (
        (
            "Module Setup",
            {
                "fields": (
                    "mock_test",
                    "module_type",
                    "duration_minutes",
                    "is_active",
                ),
            },
        ),
        (
            "Listening Audio (Master File)",
            {
                "fields": ("audio_file",),
                "description": (
                    "Continuous master audio for the entire Listening exam. "
                    "If uploaded, candidates listen to this single file across all parts. "
                    "If blank, you can upload separate audio for each part in the sections below."
                ),
            },
        ),
        (
            "Module Instructions",
            {
                "fields": ("instructions",),
                "classes": ("collapse",),
                "description": "Optional instructions shown at module start.",
            },
        ),
    )

    @admin.display(description="Mock Test")
    def mock_test_link(self, obj):
        url = reverse("admin:bcl_ieltsmocktest_change", args=[obj.mock_test.pk])
        return format_html('<a href="{}"><b>{}</b></a>', url, obj.mock_test.title)

    @admin.display(description="Module Type")
    def module_type_badge(self, obj):
        icon = {"listening": "🎧", "reading": "📖", "writing": "✍️"}.get(obj.module_type, "")
        return format_html(
            '<span class="admin-badge badge-{}">{} {}</span>',
            obj.module_type,
            icon,
            obj.get_module_type_display(),
        )

    @admin.display(description="Sections & Parts")
    def sections_link(self, obj):
        count = obj.sections.count()
        q_count = sum(s.questions.count() for s in obj.sections.all())
        url = reverse("admin:bcl_examsection_changelist") + f"?module__id__exact={obj.pk}"
        return format_html(
            '<a class="admin-action-link" href="{}"><b>{} sections</b> ({} Qs) ➔</a>',
            url,
            count,
            q_count,
        )

    @admin.display(description="Audio Mode")
    def audio_status(self, obj):
        if obj.module_type != "listening":
            return "—"
        if obj.audio_file:
            return format_html('<span class="admin-badge badge-published">🎵 Master Audio OK</span>')
        return format_html('<span class="admin-badge badge-draft">Part-by-part audio</span>')


# ==============================================================================
# 5. EXAM SECTION ADMIN
# ==============================================================================

@admin.register(ExamSection)
class ExamSectionAdmin(QuestionSetterBaseAdmin):
    form = ExamSectionAdminForm

    list_display = (
        "order",
        "title",
        "mock_test_title",
        "module_badge",
        "questions_link",
        "has_passage_badge",
        "has_audio_badge",
        "has_image_badge",
    )
    list_display_links = ("order", "title")
    list_filter = (
        "module__mock_test",
        "module__module_type",
    )
    search_fields = (
        "title",
        "passage",
        "instructions",
        "passage_instructions",
        "module__mock_test__title",
    )
    autocomplete_fields = ["module"]
    list_select_related = (
        "module",
        "module__mock_test",
    )
    inlines = [QuestionInline]

    fieldsets = (
        (
            "Section Placement",
            {
                "fields": (
                    "module",
                    "order",
                    "title",
                ),
                "description": "Select the parent module and set the sequential order (e.g. Part 1, Part 2, Passage 1).",
            },
        ),
        (
            "Reading Passage & Visual Context (Left-Side Screen)",
            {
                "fields": (
                    "passage_instructions",
                    "passage",
                    "image",
                ),
                "description": (
                    "Content displayed in the left-hand panel during the exam. "
                    "For Reading, paste the full passage text here. "
                    "For Writing Task 1, upload the chart/diagram in Image and write the task prompt in Passage."
                ),
            },
        ),
        (
            "Questions Header (Right-Side Screen)",
            {
                "fields": ("instructions",),
                "description": "Instructions shown above questions in the right-hand panel (e.g. 'Questions 1–6: Choose True, False or Not Given').",
            },
        ),
        (
            "Section Audio (Listening Only)",
            {
                "fields": ("audio_file",),
                "description": (
                    "Upload audio specific to this section if the parent Listening module "
                    "does not have a continuous master audio recording."
                ),
            },
        ),
    )

    @admin.display(description="Mock Test")
    def mock_test_title(self, obj):
        url = reverse("admin:bcl_ieltsmocktest_change", args=[obj.module.mock_test.pk])
        return format_html('<a href="{}">{}</a>', url, obj.module.mock_test.title)

    @admin.display(description="Module")
    def module_badge(self, obj):
        icon = {"listening": "🎧", "reading": "📖", "writing": "✍️"}.get(obj.module.module_type, "")
        return format_html(
            '<span class="admin-badge badge-{}">{} {}</span>',
            obj.module.module_type,
            icon,
            obj.module.get_module_type_display(),
        )

    @admin.display(description="Questions")
    def questions_link(self, obj):
        count = obj.questions.count()
        url = reverse("admin:bcl_question_changelist") + f"?section__id__exact={obj.pk}"
        return format_html(
            '<a class="admin-action-link" href="{}"><b>{} questions</b> ➔</a>',
            url,
            count,
        )

    @admin.display(description="Passage")
    def has_passage_badge(self, obj):
        if obj.passage:
            words = len(obj.passage.split())
            return format_html('<span class="admin-badge badge-reading">✓ {} words</span>', words)
        return format_html('<span class="admin-badge badge-draft">—</span>')

    @admin.display(description="Audio")
    def has_audio_badge(self, obj):
        if obj.audio_file:
            return format_html('<span class="admin-badge badge-listening">🎵 Audio</span>')
        return "—"

    @admin.display(description="Image")
    def has_image_badge(self, obj):
        if obj.image:
            return format_html('<span class="admin-badge badge-neutral">🖼 Image</span>')
        return "—"


# ==============================================================================
# 6. QUESTION ADMIN
# ==============================================================================

@admin.register(Question)
class QuestionAdmin(QuestionSetterBaseAdmin):
    form = QuestionAdminForm

    list_display = (
        "order",
        "mock_test_title",
        "module_badge",
        "section_link",
        "question_type_badge",
        "short_question",
        "options_summary",
        "correct_answer_preview",
        "marks",
    )
    list_display_links = ("order", "short_question")
    list_filter = (
        "section__module__mock_test",
        "section__module__module_type",
        "question_type",
        "section",
    )
    search_fields = (
        "question_text",
        "question_instructions",
        "correct_answer",
        "explanation",
        "section__title",
        "section__module__mock_test__title",
    )
    autocomplete_fields = ["section"]
    list_select_related = (
        "section",
        "section__module",
        "section__module__mock_test",
    )
    inlines = [QuestionOptionInline]

    fieldsets = (
        (
            "1. Question Hierarchy & Type",
            {
                "fields": (
                    "section",
                    "order",
                    "question_type",
                    "marks",
                    "answer_count",
                ),
                "description": "Select the section, the question number (order), type, and marks.",
            },
        ),
        (
            "2. Question Prompt & Instructions",
            {
                "fields": (
                    "question_instructions",
                    "question_text",
                ),
                "description": (
                    "Instructions: Optional note shown directly above this question item (e.g. 'Questions 1–5'). "
                    "Question Text: The prompt or sentence. For Fill in Blanks, type '___' (3 underscores) for each blank."
                ),
            },
        ),
        (
            "3. Media, Tables & Structured Diagrams (Optional)",
            {
                "fields": ("image", "table_content"),
                "classes": ("collapse",),
                "description": (
                    "Optional diagram/map image or HTML table structure. "
                    "Each question can include an image, table, or both."
                ),
            },
        ),
        (
            "4. Answer Key & Scoring Guide",
            {
                "fields": ("correct_answer", "explanation"),
                "description": (
                    "★ ANSWER KEY FORMATTING GUIDE:\n"
                    "• FILL IN THE BLANK: Separate multiple blanks with ';;;' and alternative acceptable answers with '/' or '||' (e.g. 9:00 am / 9 am ;;; 25 / twenty-five).\n"
                    "• MULTIPLE CHOICE: Enter the correct key (e.g. A or B) here, OR mark 'Is correct' in the Options below.\n"
                    "• MULTI-SELECT: Enter comma-separated keys (e.g. A, C).\n"
                    "• TRUE / FALSE / NOT GIVEN: Enter TRUE, FALSE, or NOT GIVEN.\n"
                    "• YES / NO / NOT GIVEN: Enter YES, NO, or NOT GIVEN.\n"
                    "• MATCHING / MATCHING INFO: Enter the matching option key (e.g. B or iv).\n"
                    "• WRITING / ESSAY: Leave blank (evaluated manually by staff examiner)."
                ),
            },
        ),
        (
            "5. Detailed Explanation & Passage Highlighting (Optional)",
            {
                "fields": (
                    "answer_location",
                    "passage_excerpt",
                    "what_question_asks",
                    "what_passage_says",
                    "why_answer",
                    "paraphrase",
                    "tip",
                ),
                "classes": ("collapse",),
                "description": (
                    "Structured explanation fields for interactive candidate review. "
                    "When provided, 'passage_excerpt' is automatically highlighted in the reading passage."
                ),
            },
        ),
    )

    @admin.display(description="Question Prompt")
    def short_question(self, obj):
        text = obj.question_text.strip().replace("\n", " ")
        if len(text) > 75:
            return text[:75] + "…"
        return text or "—"

    @admin.display(description="Mock Test")
    def mock_test_title(self, obj):
        return obj.section.module.mock_test.title

    @admin.display(description="Module")
    def module_badge(self, obj):
        m_type = obj.section.module.module_type
        icon = {"listening": "🎧", "reading": "📖", "writing": "✍️"}.get(m_type, "")
        return format_html(
            '<span class="admin-badge badge-{}">{} {}</span>',
            m_type,
            icon,
            obj.section.module.get_module_type_display(),
        )

    @admin.display(description="Section")
    def section_link(self, obj):
        url = reverse("admin:bcl_examsection_change", args=[obj.section.pk])
        return format_html('<a href="{}">{}</a>', url, obj.section.title)

    @admin.display(description="Type")
    def question_type_badge(self, obj):
        return format_html(
            '<span class="admin-badge badge-qtype">{}</span>',
            obj.get_question_type_display(),
        )

    @admin.display(description="Options")
    def options_summary(self, obj):
        opts = list(obj.options.all())
        if not opts:
            return "—"
        correct = [o.option_key for o in opts if o.is_correct]
        corr_text = f" (Correct: {', '.join(correct)})" if correct else ""
        return format_html('<span class="admin-badge badge-neutral">{} choices{}</span>', len(opts), corr_text)

    @admin.display(description="Answer Key")
    def correct_answer_preview(self, obj):
        if not obj.correct_answer:
            return format_html('<span style="color:#94a3b8;">Manual / None</span>')
        ans = obj.correct_answer.strip()
        if len(ans) > 40:
            ans = ans[:40] + "…"
        return format_html('<code class="code-preview">{}</code>', ans)


# ==============================================================================
# 7. QUESTION OPTION ADMIN
# ==============================================================================

@admin.register(QuestionOption)
class QuestionOptionAdmin(QuestionSetterBaseAdmin):
    list_display = (
        "id",
        "mock_test_title",
        "question_link",
        "option_key",
        "option_text",
        "is_correct_badge",
        "order",
    )
    list_display_links = ("id", "option_key")
    list_filter = (
        "question__section__module__mock_test",
        "question__section__module__module_type",
        "is_correct",
    )
    search_fields = (
        "option_text",
        "option_key",
        "question__question_text",
    )
    autocomplete_fields = ["question"]
    list_select_related = (
        "question",
        "question__section",
        "question__section__module",
        "question__section__module__mock_test",
    )

    @admin.display(description="Mock Test")
    def mock_test_title(self, obj):
        return obj.question.section.module.mock_test.title

    @admin.display(description="Question")
    def question_link(self, obj):
        url = reverse("admin:bcl_question_change", args=[obj.question.pk])
        short = obj.question.question_text[:50]
        return format_html('<a href="{}">Q{}: {}</a>', url, obj.question.order, short)

    @admin.display(description="Correct?")
    def is_correct_badge(self, obj):
        if obj.is_correct:
            return format_html('<span class="admin-badge badge-published">✓ Correct</span>')
        return format_html('<span style="color:#94a3b8;">✗</span>')


# ==============================================================================
# 8. CANDIDATE ATTEMPTS & EVALUATION ADMIN (AUDIT & READONLY)
# ==============================================================================

@admin.register(FullMockAttempt)
class FullMockAttemptAdmin(QuestionSetterBaseAdmin):
    list_display = (
        "id",
        "candidate",
        "mock_test",
        "status",
        "current_step",
        "overall_band_score",
        "submitted_at",
        "view_result_btn",
        "export_pdf_btn",
        "export_docx_btn",
    )
    list_filter = (
        "status",
        "current_step",
        "started_at",
    )
    search_fields = (
        "candidate__username",
        "candidate__email",
        "mock_test__title",
    )
    readonly_fields = (
        "candidate",
        "mock_test",
        "status",
        "current_step",
        "reading_attempt",
        "listening_attempt",
        "writing_attempt",
        "overall_band_score",
        "started_at",
        "submitted_at",
        "result_actions_card",
    )
    list_select_related = (
        "candidate",
        "mock_test",
        "reading_attempt",
        "listening_attempt",
        "writing_attempt",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Result")
    def view_result_btn(self, obj):
        url = reverse("bcl:full_mock_result", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" target="_blank" style="padding: 2px 7px; font-size: 11px; background: #0284c7; color: white; border-radius: 4px; text-decoration: none; font-weight: 600;">👁️ Result</a>',
            url,
        )

    @admin.display(description="PDF")
    def export_pdf_btn(self, obj):
        url = reverse("bcl:export_full_mock_attempt", args=[obj.pk, "pdf"])
        return format_html(
            '<a class="button" href="{}" target="_blank" style="padding: 2px 7px; font-size: 11px; background: #dc2626; color: white; border-radius: 4px; text-decoration: none; font-weight: 600;">📄 PDF</a>',
            url,
        )

    @admin.display(description="DOCX")
    def export_docx_btn(self, obj):
        url = reverse("bcl:export_full_mock_attempt", args=[obj.pk, "docx"])
        return format_html(
            '<a class="button" href="{}" target="_blank" style="padding: 2px 7px; font-size: 11px; background: #2563eb; color: white; border-radius: 4px; text-decoration: none; font-weight: 600;">📝 DOCX</a>',
            url,
        )

    @admin.display(description="Result Actions & Exports")
    def result_actions_card(self, obj):
        if not obj or not obj.pk:
            return "-"
        result_url = reverse("bcl:full_mock_result", args=[obj.pk])
        pdf_url = reverse("bcl:export_full_mock_attempt", args=[obj.pk, "pdf"])
        docx_url = reverse("bcl:export_full_mock_attempt", args=[obj.pk, "docx"])
        return format_html(
            '<div style="display: flex; gap: 10px; align-items: center; padding: 6px 0;">'
            '<a class="button" href="{}" target="_blank" style="padding: 6px 14px; background: #0284c7; color: white; border-radius: 5px; text-decoration: none; font-weight: 600;">👁️ View Full Mock Result</a>'
            '<a class="button" href="{}" target="_blank" style="padding: 6px 14px; background: #dc2626; color: white; border-radius: 5px; text-decoration: none; font-weight: 600;">📄 Export Official PDF</a>'
            '<a class="button" href="{}" target="_blank" style="padding: 6px 14px; background: #2563eb; color: white; border-radius: 5px; text-decoration: none; font-weight: 600;">📝 Export Word DOCX</a>'
            '</div>',
            result_url, pdf_url, docx_url,
        )


@admin.register(CandidateAttempt)
class CandidateAttemptAdmin(QuestionSetterBaseAdmin):
    list_display = (
        "id",
        "candidate",
        "module",
        "full_mock",
        "status",
        "submitted_at",
        "raw_score",
        "band_score",
        "view_result_btn",
        "export_pdf_btn",
        "export_docx_btn",
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
        "full_mock",
        "status",
        "started_at",
        "expires_at",
        "submitted_at",
        "violation_count",
        "raw_score",
        "band_score",
        "result_actions_card",
    )
    list_select_related = (
        "candidate",
        "module",
        "module__mock_test",
        "full_mock",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Result")
    def view_result_btn(self, obj):
        url = reverse("bcl:exam_result", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" target="_blank" style="padding: 2px 7px; font-size: 11px; background: #0284c7; color: white; border-radius: 4px; text-decoration: none; font-weight: 600;">👁️ Result</a>',
            url,
        )

    @admin.display(description="PDF")
    def export_pdf_btn(self, obj):
        url = reverse("bcl:export_candidate_attempt", args=[obj.pk, "pdf"])
        return format_html(
            '<a class="button" href="{}" target="_blank" style="padding: 2px 7px; font-size: 11px; background: #dc2626; color: white; border-radius: 4px; text-decoration: none; font-weight: 600;">📄 PDF</a>',
            url,
        )

    @admin.display(description="DOCX")
    def export_docx_btn(self, obj):
        url = reverse("bcl:export_candidate_attempt", args=[obj.pk, "docx"])
        return format_html(
            '<a class="button" href="{}" target="_blank" style="padding: 2px 7px; font-size: 11px; background: #2563eb; color: white; border-radius: 4px; text-decoration: none; font-weight: 600;">📝 DOCX</a>',
            url,
        )

    @admin.display(description="Result Actions & Exports")
    def result_actions_card(self, obj):
        if not obj or not obj.pk:
            return "-"
        result_url = reverse("bcl:exam_result", args=[obj.pk])
        pdf_url = reverse("bcl:export_candidate_attempt", args=[obj.pk, "pdf"])
        docx_url = reverse("bcl:export_candidate_attempt", args=[obj.pk, "docx"])
        review_button_html = ""
        if obj.module.module_type == ExamModule.ModuleType.WRITING:
            review_url = reverse("bcl:writing_review_detail", args=[obj.pk])
            review_button_html = f'<a class="button" href="{review_url}" target="_blank" style="padding: 6px 14px; background: #d97706; color: white; border-radius: 5px; text-decoration: none; font-weight: 600;">✍️ Writing Review</a>'

        return format_html(
            '<div style="display: flex; gap: 10px; align-items: center; padding: 6px 0;">'
            '<a class="button" href="{}" target="_blank" style="padding: 6px 14px; background: #0284c7; color: white; border-radius: 5px; text-decoration: none; font-weight: 600;">👁️ View Result</a>'
            '<a class="button" href="{}" target="_blank" style="padding: 6px 14px; background: #dc2626; color: white; border-radius: 5px; text-decoration: none; font-weight: 600;">📄 Export PDF</a>'
            '<a class="button" href="{}" target="_blank" style="padding: 6px 14px; background: #2563eb; color: white; border-radius: 5px; text-decoration: none; font-weight: 600;">📝 Export DOCX</a>'
            '{}'
            '</div>',
            result_url, pdf_url, docx_url, mark_safe(review_button_html),
        )


@admin.register(CandidateAnswer)
class CandidateAnswerAdmin(QuestionSetterBaseAdmin):
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


@admin.register(WritingEvaluation)
class WritingEvaluationAdmin(QuestionSetterBaseAdmin):
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


# ==============================================================================
# 9. ENHANCED ADMIN DASHBOARD CONTEXT
# ==============================================================================

_orig_admin_index = admin.site.index


def custom_admin_index(request, extra_context=None):
    extra_context = extra_context or {}
    User = get_user_model()

    total_students = User.objects.filter(is_staff=False, is_superuser=False).count()
    total_mock_tests = IELTSMockTest.objects.count()
    total_module_attempts = CandidateAttempt.objects.exclude(status=CandidateAttempt.AttemptStatus.IN_PROGRESS).count()
    total_full_mocks = FullMockAttempt.objects.exclude(status=FullMockAttempt.AttemptStatus.IN_PROGRESS).count()

    # Pending writing count: submitted writing attempts with fewer than 2 graded tasks
    pending_writing = (
        CandidateAttempt.objects.filter(module__module_type=ExamModule.ModuleType.WRITING)
        .exclude(status=CandidateAttempt.AttemptStatus.IN_PROGRESS)
        .annotate(graded_tasks=Count("task_evaluations", distinct=True))
        .filter(graded_tasks__lt=2)
        .count()
    )

    # Recent student results (Reading, Listening, Writing)
    recent_student_results = (
        CandidateAttempt.objects.exclude(status=CandidateAttempt.AttemptStatus.IN_PROGRESS)
        .select_related("candidate", "module", "module__mock_test")
        .prefetch_related("task_evaluations")
        .order_by("-submitted_at", "-started_at")[:30]
    )

    # Recent full mock attempts
    recent_full_mocks = (
        FullMockAttempt.objects.exclude(status=FullMockAttempt.AttemptStatus.IN_PROGRESS)
        .select_related("candidate", "mock_test", "reading_attempt", "listening_attempt", "writing_attempt")
        .order_by("-submitted_at", "-started_at")[:20]
    )

    extra_context.update({
        "total_students": total_students,
        "total_mock_tests": total_mock_tests,
        "total_module_attempts": total_module_attempts,
        "total_full_mocks": total_full_mocks,
        "pending_writing": pending_writing,
        "recent_student_results": recent_student_results,
        "recent_full_mocks": recent_full_mocks,
    })

    return _orig_admin_index(request, extra_context=extra_context)


admin.site.index = custom_admin_index

