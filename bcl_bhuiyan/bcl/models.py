
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


# ==========================================
# 1. IELTS MOCK TEST
# ==========================================

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


# ==========================================
# 2. EXAM MODULES
# ==========================================

class ExamModule(models.Model):

    class ModuleType(models.TextChoices):
        READING = "reading", "Reading"
        LISTENING = "listening", "Listening"
        WRITING = "writing", "Writing"

    mock_test = models.ForeignKey(
        IELTSMockTest,
        on_delete=models.CASCADE,
        related_name="modules"
    )

    module_type = models.CharField(
        max_length=20,
        choices=ModuleType.choices
    )

    duration_minutes = models.PositiveIntegerField(default=60)

    instructions = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["mock_test", "module_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["mock_test", "module_type"],
                name="unique_module_per_mock_test"
            )
        ]

    def __str__(self):
        return (
            f"{self.mock_test.title} - "
            f"{self.get_module_type_display()}"
        )


# ==========================================
# 3. EXAM SECTIONS
# ==========================================

class ExamSection(models.Model):

    module = models.ForeignKey(
        ExamModule,
        on_delete=models.CASCADE,
        related_name="sections"
    )

    title = models.CharField(max_length=255)

    instructions = models.TextField(blank=True)

    passage = models.TextField(
        blank=True,
        help_text="Reading passage or supporting text."
    )

    audio_file = models.FileField(
        upload_to="ielts/audio/",
        blank=True,
        null=True
    )

    image = models.ImageField(
        upload_to="ielts/images/",
        blank=True,
        null=True
    )

    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["module", "order"],
                name="unique_section_order_per_module"
            )
        ]

    def __str__(self):
        return f"{self.module} - {self.title}"


# ==========================================
# 4. QUESTIONS
# ==========================================

class Question(models.Model):

    class QuestionType(models.TextChoices):
        MCQ = "mcq", "Multiple Choice"
        TRUE_FALSE_NOT_GIVEN = (
            "tfng",
            "True / False / Not Given"
        )
        YES_NO_NOT_GIVEN = (
            "ynng",
            "Yes / No / Not Given"
        )
        FILL_BLANK = "fill_blank", "Fill in the Blank"
        SHORT_ANSWER = "short_answer", "Short Answer"
        MATCHING = "matching", "Matching"
        ESSAY = "essay", "Writing Task"

    section = models.ForeignKey(
        ExamSection,
        on_delete=models.CASCADE,
        related_name="questions"
    )

    question_type = models.CharField(
        max_length=30,
        choices=QuestionType.choices
    )

    question_text = models.TextField()

    order = models.PositiveIntegerField(default=1)

    marks = models.PositiveIntegerField(default=1)

    correct_answer = models.TextField(
        blank=True,
        help_text=(
            "Canonical answer for auto-marked questions. "
            "Leave blank for manually evaluated writing."
        )
    )

    explanation = models.TextField(blank=True)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["section", "order"],
                name="unique_question_order_per_section"
            )
        ]

    def __str__(self):
        return (
            f"Question {self.order} - "
            f"{self.section.title}"
        )


# ==========================================
# 5. MULTIPLE CHOICE OPTIONS
# ==========================================

class QuestionOption(models.Model):

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="options"
    )

    option_text = models.CharField(max_length=500)

    option_key = models.CharField(
        max_length=10,
        help_text="Example: A, B, C, D"
    )

    is_correct = models.BooleanField(default=False)

    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["question", "option_key"],
                name="unique_option_key_per_question"
            ),
            models.UniqueConstraint(
                fields=["question", "order"],
                name="unique_option_order_per_question"
            )
        ]

    def __str__(self):
        return f"{self.option_key}: {self.option_text}"


# ==========================================
# 6. CANDIDATE TEST ATTEMPTS
# ==========================================

class CandidateAttempt(models.Model):

    class AttemptStatus(models.TextChoices):
        IN_PROGRESS = "in_progress", "In Progress"
        SUBMITTED = "submitted", "Submitted"
        AUTO_SUBMITTED = "auto_submitted", "Auto Submitted"
        EXPIRED = "expired", "Expired"

    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ielts_attempts"
    )

    module = models.ForeignKey(
        ExamModule,
        on_delete=models.PROTECT,
        related_name="attempts"
    )

    status = models.CharField(
        max_length=20,
        choices=AttemptStatus.choices,
        default=AttemptStatus.IN_PROGRESS
    )

    started_at = models.DateTimeField(default=timezone.now)

    expires_at = models.DateTimeField(
        help_text="Server-authoritative exam deadline."
    )

    submitted_at = models.DateTimeField(
        blank=True,
        null=True
    )

    violation_count = models.PositiveIntegerField(default=0)

    raw_score = models.PositiveIntegerField(
        blank=True,
        null=True
    )

    band_score = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        validators=[
            MinValueValidator(Decimal("0.0")),
            MaxValueValidator(Decimal("9.0"))
        ],
        blank=True,
        null=True
    )

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return (
            f"{self.candidate.username} - "
            f"{self.module} - {self.status}"
        )

    def clean(self):
        super().clean()

        if self.started_at and self.expires_at:
            if self.expires_at <= self.started_at:
                raise ValidationError({
                    "expires_at": (
                        "Expiry must be after the start time."
                    )
                })

        if self.submitted_at and (
            self.status == self.AttemptStatus.IN_PROGRESS
        ):
            raise ValidationError({
                "submitted_at": (
                    "An in-progress attempt cannot "
                    "have a submission timestamp."
                )
            })

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at


# ==========================================
# 7. CANDIDATE ANSWERS
# ==========================================

class CandidateAnswer(models.Model):

    attempt = models.ForeignKey(
        CandidateAttempt,
        on_delete=models.CASCADE,
        related_name="answers"
    )

    question = models.ForeignKey(
        Question,
        on_delete=models.PROTECT,
        related_name="candidate_answers"
    )

    answer_text = models.TextField(blank=True)

    is_flagged = models.BooleanField(default=False)

    is_correct = models.BooleanField(
        blank=True,
        null=True
    )

    awarded_marks = models.PositiveIntegerField(
        blank=True,
        null=True
    )

    saved_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "question"],
                name="unique_answer_per_attempt_question"
            )
        ]

    def __str__(self):
        return (
            f"{self.attempt.candidate.username} - "
            f"Question {self.question.order}"
        )

    def clean(self):
        super().clean()

        if self.attempt_id and self.question_id:
            if (
                self.attempt.module_id
                != self.question.section.module_id
            ):
                raise ValidationError(
                    "The question must belong "
                    "to the attempted exam module."
                )

        if (
            self.awarded_marks is not None
            and self.question_id
            and self.awarded_marks > self.question.marks
        ):
            raise ValidationError({
                "awarded_marks": (
                    "Awarded marks cannot exceed "
                    "the question's maximum marks."
                )
            })


# ==========================================
# 8. WRITING EVALUATION
# ==========================================

class WritingEvaluation(models.Model):

    attempt = models.OneToOneField(
        CandidateAttempt,
        on_delete=models.CASCADE,
        related_name="writing_evaluation"
    )

    examiner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="writing_evaluations"
    )

    task_achievement = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        validators=[
            MinValueValidator(Decimal("0.0")),
            MaxValueValidator(Decimal("9.0"))
        ]
    )

    coherence_cohesion = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        validators=[
            MinValueValidator(Decimal("0.0")),
            MaxValueValidator(Decimal("9.0"))
        ]
    )

    lexical_resource = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        validators=[
            MinValueValidator(Decimal("0.0")),
            MaxValueValidator(Decimal("9.0"))
        ]
    )

    grammatical_range_accuracy = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        validators=[
            MinValueValidator(Decimal("0.0")),
            MaxValueValidator(Decimal("9.0"))
        ]
    )

    feedback = models.TextField(blank=True)

    evaluated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()

        if self.attempt_id:
            if (
                self.attempt.module.module_type
                != ExamModule.ModuleType.WRITING
            ):
                raise ValidationError(
                    "Writing evaluations can only "
                    "be assigned to Writing attempts."
                )

        if self.examiner_id and not self.examiner.is_staff:
            raise ValidationError({
                "examiner": "Examiner must be a staff user."
            })

    def __str__(self):
        return (
            f"Writing Evaluation - "
            f"{self.attempt.candidate.username}"
        )
