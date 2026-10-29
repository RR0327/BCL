"""Staff-only browser workflow for manual IELTS Writing review."""
from decimal import Decimal, ROUND_HALF_UP

from django import forms
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .models import (
    CandidateAnswer, CandidateAttempt, ExamModule, Question,
    WritingTaskEvaluation, get_writing_task_questions,
)


class WritingTaskEvaluationForm(forms.ModelForm):
    class Meta:
        model = WritingTaskEvaluation
        fields = [
            "task_achievement", "coherence_cohesion", "lexical_resource",
            "grammatical_range_accuracy", "feedback",
        ]
        widgets = {
            "task_achievement": forms.NumberInput(attrs={
                "class": "score-input",
                "step": "0.5",
                "min": "0",
                "max": "9",
                "placeholder": "e.g. 6.5",
                "inputmode": "decimal",
            }),
            "coherence_cohesion": forms.NumberInput(attrs={
                "class": "score-input",
                "step": "0.5",
                "min": "0",
                "max": "9",
                "placeholder": "e.g. 6.5",
                "inputmode": "decimal",
            }),
            "lexical_resource": forms.NumberInput(attrs={
                "class": "score-input",
                "step": "0.5",
                "min": "0",
                "max": "9",
                "placeholder": "e.g. 6.5",
                "inputmode": "decimal",
            }),
            "grammatical_range_accuracy": forms.NumberInput(attrs={
                "class": "score-input",
                "step": "0.5",
                "min": "0",
                "max": "9",
                "placeholder": "e.g. 6.5",
                "inputmode": "decimal",
            }),
            "feedback": forms.Textarea(attrs={
                "rows": 5,
                "class": "feedback-textarea",
                "placeholder": "Detail candidate strengths, lexical range improvements, and grammar corrections...",
            }),
        }


def writing_result_band(attempt):
    """Use Task 1 = 1/3, Task 2 = 2/3. Round combined average to 0.5.

    This is a practice evaluation calculation, not official certification.
    """
    grades = {item.task_number: item for item in attempt.task_evaluations.all()}
    if set(grades) != {1, 2}:
        return None
    combined = (grades[1].criterion_average + 2 * grades[2].criterion_average) / Decimal("3")
    return (combined * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / Decimal("2")


@staff_member_required
@require_http_methods(["GET"])
def writing_review_list(request):
    attempts = (
        CandidateAttempt.objects.filter(module__module_type=ExamModule.ModuleType.WRITING)
        .exclude(status=CandidateAttempt.AttemptStatus.IN_PROGRESS)
        .select_related("candidate", "module", "module__mock_test")
        .annotate(graded_tasks=Count("task_evaluations", distinct=True))
        .order_by("-submitted_at")
    )
    return render(request, "writing/review_list.html", {"attempts": attempts})


@staff_member_required
@require_http_methods(["GET", "POST"])
def writing_review_detail(request, attempt_id):
    attempt = get_object_or_404(
        CandidateAttempt.objects.select_related("candidate", "module", "module__mock_test"),
        pk=attempt_id, module__module_type=ExamModule.ModuleType.WRITING,
    )
    if attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
        messages.error(request, "This attempt has not been submitted yet.")
        return redirect("bcl:writing_review_list")

    prompts = {1: [], 2: []}
    essay_questions = get_writing_task_questions(attempt.module)
    for task_number, question in enumerate(essay_questions, start=1):
        if task_number in prompts:
            prompts[task_number].append(question)

    existing = {item.task_number: item for item in attempt.task_evaluations.select_related("examiner")}
    forms_by_task = {}
    task_cards = []
    posted_task = request.POST.get("task_number") if request.method == "POST" else None
    if request.method == "POST" and posted_task not in {"1", "2"}:
        messages.error(request, "Select a valid task.")
        return redirect("bcl:writing_review_detail", attempt_id=attempt.pk)

    for n in (1, 2):
        question = prompts[n][0] if len(prompts[n]) == 1 else None
        answer = (
            CandidateAnswer.objects.filter(attempt=attempt, question=question).first()
            if question else None
        )
        instance = existing.get(n)
        form = WritingTaskEvaluationForm(
            request.POST if posted_task == str(n) else None,
            instance=instance,
            prefix=f"task{n}",
        )
        forms_by_task[n] = form
        task_cards.append({
            "number": n, "question": question, "answer": answer,
            "form": form, "evaluation": instance,
            "configuration_error": len(essay_questions) != 2 or len(prompts[n]) != 1,
        })

    if request.method == "POST":
        n = int(posted_task)
        question = prompts[n][0] if len(prompts[n]) == 1 else None
        if len(essay_questions) != 2 or not question:
            messages.error(request, "Configure exactly two Essay questions in this Writing module, ordered as Task 1 and Task 2.")
            return redirect("bcl:writing_review_detail", attempt_id=attempt.pk)
        form = forms_by_task[n]
        if form.is_valid():
            with transaction.atomic():
                # Lock this attempt while reviewing, and verify it is still closed.
                locked = CandidateAttempt.objects.select_for_update().get(pk=attempt.pk)
                if locked.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
                    messages.error(request, "Cannot grade an active attempt.")
                    return redirect("bcl:writing_review_list")
                evaluation = form.save(commit=False)
                evaluation.attempt = locked
                evaluation.question = question
                evaluation.task_number = n
                evaluation.examiner = request.user
                evaluation.full_clean()
                evaluation.save()
                band = writing_result_band(locked)
                locked.band_score = band
                locked.save(update_fields=["band_score"])
                if locked.full_mock:
                    locked.full_mock.calculate_overall_score()
                    locked.full_mock.save(update_fields=["overall_band_score"])
            messages.success(request, f"Task {n} evaluation saved.")
            return redirect("bcl:writing_review_detail", attempt_id=attempt.pk)

    return render(request, "writing/review_detail.html", {
        "attempt": attempt,
        "task_cards": task_cards,
        "overall_band": writing_result_band(attempt),
    })
