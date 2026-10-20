from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
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


class ExamModule(models.Model):
    class ModuleType(models.TextChoices):
        READING = "reading", "Reading"
        LISTENING = "listening", "Listening"
        WRITING = "writing", "Writing"

    mock_test = models.ForeignKey(IELTSMockTest, on_delete=models.CASCADE, related_name="modules")
    module_type = models.CharField(max_length=20, choices=ModuleType.choices)
    duration_minutes = models.PositiveIntegerField(default=60)
    instructions = models.TextField(blank=True)
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
    audio_file = models.FileField(upload_to="ielts/audio/", blank=True, null=True)
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
    order = models.PositiveIntegerField(default=1)
    marks = models.PositiveIntegerField(default=1)
    correct_answer = models.TextField(blank=True, help_text="Canonical answer for auto-marked questions. Leave blank for manually evaluated writing.")
    explanation = models.TextField(blank=True)

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


class CandidateAttempt(models.Model):
    class AttemptStatus(models.TextChoices):
        IN_PROGRESS = "in_progress", "In Progress"
        SUBMITTED = "submitted", "Submitted"
        AUTO_SUBMITTED = "auto_submitted", "Auto Submitted"
        EXPIRED = "expired", "Expired"

    candidate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ielts_attempts")
    module = models.ForeignKey(ExamModule, on_delete=models.PROTECT, related_name="attempts")
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
            elif self.question.section.order != self.task_number:
                errors["question"] = "Question section order must match Task 1 or Task 2."
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
