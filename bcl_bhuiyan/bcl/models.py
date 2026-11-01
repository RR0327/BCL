from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


class IELTSMockTest(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    test_number = models.PositiveIntegerField(unique=True)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["test_number"]
        verbose_name = "IELTS Mock Test"
        verbose_name_plural = "IELTS Mock Tests"

    def __str__(self):
        return f"Test {self.test_number}: {self.title}"

    @property
    def ordered_modules(self):
        """Return active modules in full-mock order: Listening, Reading, Writing."""
        order_map = {"listening": 1, "reading": 2, "writing": 3}
        return sorted(
            [m for m in self.modules.all() if m.is_active],
            key=lambda m: order_map.get(m.module_type, 99),
        )

    @property
    def has_all_modules(self):
        """Check if active Reading, Listening, and Writing modules all exist."""
        active_types = {m.module_type for m in self.modules.all() if m.is_active}
        return {"reading", "listening", "writing"}.issubset(active_types)

    @property
    def all_modules_duration_minutes(self):
        """Total duration for all 3 modules in minutes (typically 150m: 60+30+60)."""
        return sum(m.duration_minutes for m in self.ordered_modules)


class ExamModule(models.Model):
    class ModuleType(models.TextChoices):
        READING = "reading", "Reading"
        LISTENING = "listening", "Listening"
        WRITING = "writing", "Writing"

    mock_test = models.ForeignKey(IELTSMockTest, on_delete=models.CASCADE, related_name="modules")
    module_type = models.CharField(max_length=20, choices=ModuleType.choices)
    duration_minutes = models.PositiveIntegerField(default=60)
    instructions = models.TextField(blank=True)
    audio_file = models.FileField(
        upload_to="ielts/audio/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(
            allowed_extensions=["mp3", "wav", "ogg", "m4a", "aac", "webm"]
        )],
        help_text="Full continuous audio recording for this module (covers all parts/questions). If provided, this single audio will play continuously across all parts. If left blank, individual section audio files will be used instead.",
    )
    listening_html_file = models.FileField(
        upload_to="ielts/listening/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["html"])],
        help_text="Optional uploaded HTML listening test. Used for Listening modules without database sections.",
    )
    content_file = models.FileField(
        upload_to="ielts/module-content/",
        blank=True,
        null=True,
        help_text="Optional module source file. Any file extension is accepted and browser-supported formats are displayed automatically.",
    )
    module_file = models.FileField(
        upload_to="ielts/module-files/",
        blank=True,
        null=True,
        help_text="Optional file for this module. Any file extension is accepted.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["mock_test", "module_type"]
        constraints = [models.UniqueConstraint(fields=["mock_test", "module_type"], name="unique_module_per_mock_test")]

    def __str__(self):
        return f"{self.mock_test.title} - {self.get_module_type_display()}"


class ExamSection(models.Model):
    module = models.ForeignKey(ExamModule, on_delete=models.CASCADE, related_name="sections")
    title = models.CharField(max_length=255)
    instructions = models.TextField(blank=True)
    passage_instructions = models.TextField(
        blank=True,
        help_text="Instructions or introductory text shown with the passage.",
    )
    passage = models.TextField(blank=True, help_text="Reading passage or supporting text.")
    audio_file = models.FileField(
        upload_to="ielts/audio/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(
            allowed_extensions=["mp3", "wav", "ogg", "m4a", "aac", "webm"]
        )],
        help_text="Individual audio for this specific part/section (used when module-level continuous audio is not provided).",
    )
    image = models.ImageField(upload_to="ielts/images/", blank=True, null=True)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]
        constraints = [models.UniqueConstraint(fields=["module", "order"], name="unique_section_order_per_module")]

    def __str__(self):
        return f"{self.module} - {self.title}"


class Question(models.Model):
    class QuestionType(models.TextChoices):
        MCQ = "mcq", "Multiple Choice"
        TRUE_FALSE_NOT_GIVEN = "tfng", "True / False / Not Given"
        YES_NO_NOT_GIVEN = "ynng", "Yes / No / Not Given"
        FILL_BLANK = "fill_blank", "Fill in the Blank"
        SHORT_ANSWER = "short_answer", "Short Answer"
        MATCHING = "matching", "Matching"
        MATCHING_INFORMATION = "matching_information", "Matching Information"
        MULTI_SELECT = "multi_select", "Multi-Select"
        MAP_LABELLING = "map_labelling", "Map / Diagram Labelling"
        ESSAY = "essay", "Writing Task"

    section = models.ForeignKey(ExamSection, on_delete=models.CASCADE, related_name="questions")
    question_type = models.CharField(max_length=30, choices=QuestionType.choices)
    question_text = models.TextField()
    question_instructions = models.TextField(
        blank=True,
        help_text="Optional instructions shown directly above this question.",
    )
    answer_count = models.PositiveIntegerField(
        default=1,
        help_text="Number of answer fields for fill-in-the-blank questions. Use ___ in the prompt for inline fields.",
    )
    image = models.ImageField(
        upload_to="ielts/questions/images/",
        blank=True,
        null=True,
        help_text="Optional figure or diagram image for this question.",
    )
    table_content = models.TextField(
        blank=True,
        help_text="Optional HTML or markdown table content for this question.",
    )
    order = models.PositiveIntegerField(default=1)
    marks = models.PositiveIntegerField(default=1)
    correct_answer = models.TextField(blank=True, help_text="Canonical answer for auto-marked questions. Leave blank for manually evaluated writing.")
    explanation = models.TextField(blank=True)
    passage_excerpt = models.TextField(
        blank=True,
        help_text="Exact excerpt from the passage used to highlight the text in the passage.",
    )
    answer_location = models.CharField(
        max_length=255,
        blank=True,
        help_text="Location in passage, e.g. 'Paragraph 1'.",
    )
    what_question_asks = models.TextField(
        blank=True,
        help_text="Analysis of what the question asks.",
    )
    what_passage_says = models.TextField(
        blank=True,
        help_text="Breakdown of relevant passage statement.",
    )
    why_answer = models.TextField(
        blank=True,
        help_text="Detailed justification of why this answer is correct.",
    )
    paraphrase = models.TextField(
        blank=True,
        help_text="Paraphrase mapping, e.g. question -> passage.",
    )
    tip = models.TextField(
        blank=True,
        help_text="Exam tip or trap alert.",
    )

    @property
    def has_rich_explanation(self):
        return bool(
            self.passage_excerpt
            or self.answer_location
            or self.what_question_asks
            or self.what_passage_says
            or self.why_answer
            or self.paraphrase
            or self.tip
        )

    class Meta:
        ordering = ["order", "id"]
        constraints = [models.UniqueConstraint(fields=["section", "order"], name="unique_question_order_per_section")]

    def __str__(self):
        return f"Question {self.order} - {self.section.title}"


class QuestionOption(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    option_text = models.CharField(
        max_length=500,
        blank=True,
        help_text="Optional description shown beside the option key.",
    )
    option_key = models.CharField(max_length=10, help_text="Example: A, B, C, D")
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["question", "option_key"], name="unique_option_key_per_question"),
            models.UniqueConstraint(fields=["question", "order"], name="unique_option_order_per_question"),
        ]

    def __str__(self):
        return f"{self.option_key}: {self.option_text}"


def get_writing_task_questions(module):
    """Return essay prompts in task order, including tests storing both in one section."""
    return list(
        Question.objects.filter(
            section__module=module,
            question_type=Question.QuestionType.ESSAY,
        )
        .select_related("section")
        .order_by("section__order", "order", "pk")
    )


class FullMockAttempt(models.Model):
    class AttemptStatus(models.TextChoices):
        IN_PROGRESS = "in_progress", "In Progress"
        SUBMITTED = "submitted", "Submitted"
        AUTO_SUBMITTED = "auto_submitted", "Auto Submitted"

    candidate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="full_mock_attempts")
    mock_test = models.ForeignKey(IELTSMockTest, on_delete=models.CASCADE, related_name="full_mock_attempts")
    status = models.CharField(max_length=20, choices=AttemptStatus.choices, default=AttemptStatus.IN_PROGRESS)
    current_step = models.CharField(
        max_length=20,
        default="listening",
        help_text="Current active module step: listening, reading, writing, or completed.",
    )
    reading_attempt = models.ForeignKey(
        "CandidateAttempt",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="as_full_mock_reading",
    )
    listening_attempt = models.ForeignKey(
        "CandidateAttempt",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="as_full_mock_listening",
    )
    writing_attempt = models.ForeignKey(
        "CandidateAttempt",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="as_full_mock_writing",
    )
    started_at = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(null=True, blank=True)
    overall_band_score = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        validators=[MinValueValidator(Decimal("0.0")), MaxValueValidator(Decimal("9.0"))],
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "All-Module Full Mock Attempt"
        verbose_name_plural = "All-Module Full Mock Attempts"

    def __str__(self):
        return f"{self.candidate.username} - {self.mock_test.title} (All Modules) - {self.status}"

    def calculate_overall_score(self):
        scores = []
        for att in [self.reading_attempt, self.listening_attempt, self.writing_attempt]:
            if att and att.band_score is not None:
                scores.append(float(att.band_score))
        if len(scores) == 3:
            avg = sum(scores) / 3.0
            remainder = avg % 1
            base = int(avg)
            if remainder < 0.25:
                final = base
            elif remainder < 0.75:
                final = base + 0.5
            else:
                final = base + 1.0
            self.overall_band_score = Decimal(str(final))
        elif len(scores) > 0:
            avg = sum(scores) / len(scores)
            remainder = avg % 1
            base = int(avg)
            if remainder < 0.25:
                final = base
            elif remainder < 0.75:
                final = base + 0.5
            else:
                final = base + 1.0
            self.overall_band_score = Decimal(str(final))
        return self.overall_band_score


class CandidateAttempt(models.Model):
    class AttemptStatus(models.TextChoices):
        IN_PROGRESS = "in_progress", "In Progress"
        SUBMITTED = "submitted", "Submitted"
        AUTO_SUBMITTED = "auto_submitted", "Auto Submitted"
        EXPIRED = "expired", "Expired"

    candidate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ielts_attempts")
    module = models.ForeignKey(ExamModule, on_delete=models.PROTECT, related_name="attempts")
    full_mock = models.ForeignKey(
        FullMockAttempt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="module_attempts",
        help_text="Associated All-Module Full Mock Attempt if part of combined testing.",
    )
    status = models.CharField(max_length=20, choices=AttemptStatus.choices, default=AttemptStatus.IN_PROGRESS)
    started_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(help_text="Server-authoritative exam deadline.")
    submitted_at = models.DateTimeField(blank=True, null=True)
    violation_count = models.PositiveIntegerField(default=0)
    raw_score = models.PositiveIntegerField(blank=True, null=True)
    band_score = models.DecimalField(
        max_digits=3, decimal_places=1,
        validators=[MinValueValidator(Decimal("0.0")), MaxValueValidator(Decimal("9.0"))],
        blank=True, null=True,
    )
    answers_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Stores candidate submitted answers payload (e.g. for HTML-based Listening modules).",
    )

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.candidate.username} - {self.module} - {self.status}"

    def clean(self):
        super().clean()
        if self.started_at and self.expires_at and self.expires_at <= self.started_at:
            raise ValidationError({"expires_at": "Expiry must be after the start time."})
        if self.submitted_at and self.status == self.AttemptStatus.IN_PROGRESS:
            raise ValidationError({"submitted_at": "An in-progress attempt cannot have a submission timestamp."})

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at


class CandidateAnswer(models.Model):
    attempt = models.ForeignKey(CandidateAttempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="candidate_answers")
    answer_text = models.TextField(blank=True)
    is_flagged = models.BooleanField(default=False)
    is_correct = models.BooleanField(blank=True, null=True)
    awarded_marks = models.PositiveIntegerField(blank=True, null=True)
    saved_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["attempt", "question"], name="unique_answer_per_attempt_question")]

    def __str__(self):
        return f"{self.attempt.candidate.username} - Question {self.question.order}"

    def clean(self):
        super().clean()
        if self.attempt_id and self.question_id and self.attempt.module_id != self.question.section.module_id:
            raise ValidationError("The question must belong to the attempted exam module.")
        if self.awarded_marks is not None and self.question_id and self.awarded_marks > self.question.marks:
            raise ValidationError({"awarded_marks": "Awarded marks cannot exceed the question's maximum marks."})


# Legacy initial one-record Writing evaluation. Preserved for migration/data compatibility.
# New evaluations should be created using WritingTaskEvaluation below.
class WritingEvaluation(models.Model):
    attempt = models.OneToOneField(CandidateAttempt, on_delete=models.CASCADE, related_name="writing_evaluation")
    examiner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="writing_evaluations")
    task_achievement = models.DecimalField(max_digits=3, decimal_places=1, validators=[MinValueValidator(Decimal("0.0")), MaxValueValidator(Decimal("9.0"))])
    coherence_cohesion = models.DecimalField(max_digits=3, decimal_places=1, validators=[MinValueValidator(Decimal("0.0")), MaxValueValidator(Decimal("9.0"))])
    lexical_resource = models.DecimalField(max_digits=3, decimal_places=1, validators=[MinValueValidator(Decimal("0.0")), MaxValueValidator(Decimal("9.0"))])
    grammatical_range_accuracy = models.DecimalField(max_digits=3, decimal_places=1, validators=[MinValueValidator(Decimal("0.0")), MaxValueValidator(Decimal("9.0"))])
    feedback = models.TextField(blank=True)
    evaluated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.attempt_id and self.attempt.module.module_type != ExamModule.ModuleType.WRITING:
            raise ValidationError("Writing evaluations can only be assigned to Writing attempts.")
        if self.examiner_id and not self.examiner.is_staff:
            raise ValidationError({"examiner": "Examiner must be a staff user."})

    def __str__(self):
        return f"Writing Evaluation - {self.attempt.candidate.username}"


class WritingTaskEvaluation(models.Model):
    """One examiner assessment per task, per submitted Writing attempt."""
    attempt = models.ForeignKey(CandidateAttempt, on_delete=models.CASCADE, related_name="task_evaluations")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="writing_task_evaluations")
    task_number = models.PositiveSmallIntegerField(choices=[(1, "Task 1"), (2, "Task 2")])
    examiner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="writing_task_evaluations")
    task_achievement = models.DecimalField(max_digits=3, decimal_places=1)
    coherence_cohesion = models.DecimalField(max_digits=3, decimal_places=1)
    lexical_resource = models.DecimalField(max_digits=3, decimal_places=1)
    grammatical_range_accuracy = models.DecimalField(max_digits=3, decimal_places=1)
    feedback = models.TextField(blank=True)
    evaluated_at = models.DateTimeField(auto_now=True)

    SCORE_FIELDS = (
        "task_achievement", "coherence_cohesion",
        "lexical_resource", "grammatical_range_accuracy",
    )

    class Meta:
        ordering = ["task_number"]
        constraints = [
            models.UniqueConstraint(fields=["attempt", "task_number"], name="unique_writing_task_per_attempt"),
        ]

    @property
    def criterion_average(self):
        return sum((getattr(self, f) for f in self.SCORE_FIELDS), Decimal("0")) / Decimal("4")

    def clean(self):
        super().clean()
        errors = {}
        if self.attempt_id:
            if self.attempt.module.module_type != ExamModule.ModuleType.WRITING:
                errors["attempt"] = "Only Writing attempts can be graded."
            elif self.attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
                errors["attempt"] = "The candidate must submit before grading."
        if self.question_id and self.attempt_id:
            if self.question.section.module_id != self.attempt.module_id:
                errors["question"] = "The question is not in this attempt's module."
            elif self.question.question_type != Question.QuestionType.ESSAY:
                errors["question"] = "Only an Essay question can be graded."
            elif self.task_number not in {1, 2}:
                errors["task_number"] = "Writing task number must be Task 1 or Task 2."
            elif self.question.pk not in {
                question.pk
                for task_number, question in enumerate(
                    get_writing_task_questions(self.attempt.module), start=1
                )
                if task_number == self.task_number
            }:
                errors["question"] = "Question order must match the evaluated Writing task."
        if self.examiner_id and not self.examiner.is_staff:
            errors["examiner"] = "The examiner must be a staff member."
        for field in self.SCORE_FIELDS:
            score = getattr(self, field)
            if score is not None and (score < 0 or score > 9 or score * 2 != (score * 2).to_integral_value()):
                errors[field] = "Choose a score from 0 to 9 in increments of 0.5."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Attempt #{self.attempt_id} — Task {self.task_number}"

# Privacy/security event metadata; no personal response contents.
from .privacy import SecurityAuditEvent  # noqa: E402,F401
