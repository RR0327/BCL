from datetime import timedelta
import json
import logging
import uuid

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import CandidateAnswer, CandidateAttempt, ExamModule, Question
from .scoring import finalize_attempt_score


MAX_ANSWER_LENGTH = 20000
logger = logging.getLogger(__name__)


def is_candidate(user):
    return (
        user.is_authenticated
        and user.is_active
        and not user.is_staff
        and not user.is_superuser
    )


def get_remaining_seconds(attempt, now=None):
    now = now or timezone.now()
    return max(0, int((attempt.expires_at - now).total_seconds()))


def expire_attempt_if_needed(attempt):
    """Close timed-out attempts when an endpoint is requested."""
    with transaction.atomic():
        locked = CandidateAttempt.objects.select_for_update().get(pk=attempt.pk)
        now = timezone.now()
        if locked.status == CandidateAttempt.AttemptStatus.IN_PROGRESS and now >= locked.expires_at:
            locked.status = CandidateAttempt.AttemptStatus.AUTO_SUBMITTED
            locked.submitted_at = now
            locked.save(update_fields=["status", "submitted_at"])
            finalize_attempt_score(locked)
        return locked


def is_superseded_active_attempt(attempt):
    """Reject writes to legacy duplicate sessions until the start flow repairs them.

    A newer active attempt for the same candidate/module is authoritative.
    Read-only check; the start endpoint performs duplicate cleanup and scoring.
    """
    return CandidateAttempt.objects.filter(
        candidate_id=attempt.candidate_id,
        module_id=attempt.module_id,
        status=CandidateAttempt.AttemptStatus.IN_PROGRESS,
    ).filter(
        models.Q(started_at__gt=attempt.started_at)
        | models.Q(started_at=attempt.started_at, pk__gt=attempt.pk)
    ).exists()


def get_candidate_attempt(request, attempt_id):
    return get_object_or_404(
        CandidateAttempt.objects.select_related("module", "module__mock_test"),
        pk=attempt_id,
        candidate=request.user,
    )


@login_required
@require_GET
def exam_rules(request, module_id):
    if not is_candidate(request.user):
        messages.error(request, "Administrator accounts cannot take candidate examinations.")
        return redirect("bcl:dashboard")

    module = get_object_or_404(
        ExamModule.objects.select_related("mock_test"),
        pk=module_id,
        is_active=True,
        mock_test__is_published=True,
    )
    active_attempts = CandidateAttempt.objects.filter(
        candidate=request.user,
        module=module,
        status=CandidateAttempt.AttemptStatus.IN_PROGRESS,
    ).order_by("-started_at")
    for active in active_attempts:
        updated = expire_attempt_if_needed(active)
        if updated.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
            return redirect("bcl:exam_session", attempt_id=updated.pk)

    return render(request, "exam/rules.html", {"module": module, "mock_test": module.mock_test})


@login_required
@require_POST
def start_exam(request, module_id):
    if not is_candidate(request.user):
        messages.error(request, "This action is only available to candidates.")
        return redirect("bcl:dashboard")
    if request.POST.get("accept_rules") != "yes":
        messages.error(request, "You must accept the examination rules before starting.")
        return redirect("bcl:exam_rules", module_id=module_id)

    module = get_object_or_404(
        ExamModule.objects.select_related("mock_test"),
        pk=module_id,
        is_active=True,
        mock_test__is_published=True,
    )
    with transaction.atomic():
        # Row locking is effective in PostgreSQL, not in SQLite.
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        now = timezone.now()
        active = None
        existing = CandidateAttempt.objects.filter(
            candidate=request.user,
            module=module,
            status=CandidateAttempt.AttemptStatus.IN_PROGRESS,
        ).order_by("-started_at")
        for attempt in existing:
            if now >= attempt.expires_at:
                attempt.status = CandidateAttempt.AttemptStatus.AUTO_SUBMITTED
                attempt.submitted_at = now
                attempt.save(update_fields=["status", "submitted_at"])
                finalize_attempt_score(attempt)
            elif active is None:
                active = attempt
            else:
                # Legacy data may contain duplicate live attempts. Keep the
                # newest session and close the others under the candidate lock.
                # This prevents an old session from continuing to accept answers.
                attempt.status = CandidateAttempt.AttemptStatus.AUTO_SUBMITTED
                attempt.submitted_at = now
                attempt.save(update_fields=["status", "submitted_at"])
                finalize_attempt_score(attempt)
        if active is None:
            active = CandidateAttempt.objects.create(
                candidate=request.user,
                module=module,
                started_at=now,
                expires_at=now + timedelta(minutes=module.duration_minutes),
                status=CandidateAttempt.AttemptStatus.IN_PROGRESS,
            )
    return redirect("bcl:exam_session", attempt_id=active.pk)


@login_required
@require_GET
def exam_session(request, attempt_id):
    attempt = expire_attempt_if_needed(get_candidate_attempt(request, attempt_id))
    if attempt.status != CandidateAttempt.AttemptStatus.IN_PROGRESS:
        return redirect("bcl:exam_result", attempt_id=attempt.pk)

    sections = attempt.module.sections.order_by("order", "pk").prefetch_related("questions__options")
    saved_answers = list(
        CandidateAnswer.objects.filter(attempt=attempt).values(
            "question_id", "answer_text", "is_flagged"
        )
    )
    return render(request, "exam/session.html", {
        "attempt": attempt,
        "module": attempt.module,
        "mock_test": attempt.module.mock_test,
        "sections": sections,
        "remaining_seconds": get_remaining_seconds(attempt),
        "saved_answers": saved_answers,
    })


@login_required
@require_GET
def exam_timer(request, attempt_id):
    attempt = expire_attempt_if_needed(get_candidate_attempt(request, attempt_id))
    remaining = (
        get_remaining_seconds(attempt)
        if attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS else 0
    )
    return JsonResponse({
        "attempt_id": attempt.pk,
        "status": attempt.status,
        "remaining_seconds": remaining,
        "server_time": timezone.now().isoformat(),
        "expires_at": attempt.expires_at.isoformat(),
        "violation_count": attempt.violation_count,
    })


@login_required
@require_POST
def save_exam_answer(request, attempt_id):
    """Persist one answer and its review flag; scoring happens later."""
    if not is_candidate(request.user):
        return JsonResponse({"error": "Candidates only."}, status=403)

    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "Expected a JSON object."}, status=400)

    question_id = payload.get("question_id")
    answer_text = payload.get("answer_text")
    is_flagged = payload.get("is_flagged")
    if type(question_id) is not int or question_id <= 0:
        return JsonResponse({"error": "Invalid question ID."}, status=400)
    if not isinstance(answer_text, str) or len(answer_text) > MAX_ANSWER_LENGTH:
        return JsonResponse({"error": "Invalid or oversized answer."}, status=400)
    if not isinstance(is_flagged, bool):
        return JsonResponse({"error": "is_flagged must be true or false."}, status=400)

    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        attempt = get_object_or_404(
            CandidateAttempt.objects.select_for_update(),
            pk=attempt_id,
            candidate=request.user,
        )
        if (attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS
                and is_superseded_active_attempt(attempt)):
            return JsonResponse({"error": "This session was superseded by a newer active session."}, status=409)
        now = timezone.now()
        if attempt.status != CandidateAttempt.AttemptStatus.IN_PROGRESS:
            return JsonResponse({"error": "This exam is already closed."}, status=409)
        if now >= attempt.expires_at:
            attempt.status = CandidateAttempt.AttemptStatus.AUTO_SUBMITTED
            attempt.submitted_at = now
            attempt.save(update_fields=["status", "submitted_at"])
            finalize_attempt_score(attempt)
            return JsonResponse({"error": "Exam time has expired."}, status=409)

        question = get_object_or_404(
            Question.objects.prefetch_related("options"),
            pk=question_id,
            section__module_id=attempt.module_id,
        )
        value = answer_text.strip()
        if question.question_type == Question.QuestionType.MCQ and value:
            valid_keys = {option.option_key for option in question.options.all()}
            if value not in valid_keys:
                return JsonResponse({"error": "Invalid option selection."}, status=400)
        if question.question_type == Question.QuestionType.TRUE_FALSE_NOT_GIVEN and value:
            if value not in {"TRUE", "FALSE", "NOT GIVEN"}:
                return JsonResponse({"error": "Invalid TFNG answer."}, status=400)
        if question.question_type == Question.QuestionType.YES_NO_NOT_GIVEN and value:
            if value not in {"YES", "NO", "NOT GIVEN"}:
                return JsonResponse({"error": "Invalid YNNG answer."}, status=400)
        if question.question_type in {
            Question.QuestionType.MATCHING,
            Question.QuestionType.MATCHING_INFORMATION,
        } and value:
            valid_keys = {option.option_key for option in question.options.all()}
            if value not in valid_keys:
                return JsonResponse({"error": "Invalid matching selection."}, status=400)

        saved, _ = CandidateAnswer.objects.update_or_create(
            attempt=attempt,
            question=question,
            defaults={"answer_text": value, "is_flagged": is_flagged},
        )
    return JsonResponse({
        "success": True,
        "question_id": question_id,
        "answer_text": saved.answer_text,
        "is_flagged": saved.is_flagged,
        "saved_at": saved.saved_at.isoformat(),
    })


@login_required
@require_POST
def report_exam_violation(request, attempt_id):
    """Register one focus-loss incident and end an attempt on incident two.

    The browser reports focus changes; server verifies ownership, session
    state, and time. Browser signals cannot establish intent or prevent all
    cheating. This is a basic integrity control, not secure proctoring.
    """
    if not is_candidate(request.user):
        return JsonResponse({"error": "Candidates only."}, status=403)
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "Expected a JSON object."}, status=400)

    reason = payload.get("reason")
    if reason not in {"tab_hidden", "window_blur"}:
        return JsonResponse({"error": "Invalid violation reason."}, status=400)

    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        attempt = get_object_or_404(
            CandidateAttempt.objects.select_for_update(),
            pk=attempt_id, candidate=request.user,
        )
        if (attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS
                and is_superseded_active_attempt(attempt)):
            return JsonResponse({"error": "This session was superseded by a newer active session."}, status=409)
        now = timezone.now()
        if attempt.status != CandidateAttempt.AttemptStatus.IN_PROGRESS:
            return JsonResponse({"error": "Exam already closed.", "status": attempt.status}, status=409)
        if now >= attempt.expires_at:
            attempt.status = CandidateAttempt.AttemptStatus.AUTO_SUBMITTED
            attempt.submitted_at = now
            attempt.save(update_fields=["status", "submitted_at"])
            finalize_attempt_score(attempt)
            return JsonResponse({"error": "Exam time expired.", "status": attempt.status}, status=409)

        attempt.violation_count += 1
        if attempt.violation_count >= 2:
            attempt.status = CandidateAttempt.AttemptStatus.AUTO_SUBMITTED
            attempt.submitted_at = now
            attempt.save(update_fields=["violation_count", "status", "submitted_at"])
            finalize_attempt_score(attempt)
        else:
            attempt.save(update_fields=["violation_count"])
        count = attempt.violation_count
        status = attempt.status
        logger.warning(
            "Exam focus-loss report: attempt_id=%s candidate_id=%s reason=%s count=%s status=%s",
            attempt.pk, request.user.pk, reason, count, status,
        )

    return JsonResponse({
        "violation_count": count,
        "status": status,
        "warning": count == 1,
        "auto_submitted": status == CandidateAttempt.AttemptStatus.AUTO_SUBMITTED,
    })


@login_required
@require_POST
def submit_exam(request, attempt_id):
    if not is_candidate(request.user):
        return JsonResponse({"error": "Candidates only."}, status=403)
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        attempt = get_object_or_404(
            CandidateAttempt.objects.select_for_update(),
            pk=attempt_id,
            candidate=request.user,
        )
        if (attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS
                and is_superseded_active_attempt(attempt)):
            return JsonResponse({"error": "This session was superseded by a newer active session."}, status=409)
        if attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
            now = timezone.now()
            attempt.status = (
                CandidateAttempt.AttemptStatus.AUTO_SUBMITTED
                if now >= attempt.expires_at
                else CandidateAttempt.AttemptStatus.SUBMITTED
            )
            attempt.submitted_at = now
            attempt.save(update_fields=["status", "submitted_at"])
            finalize_attempt_score(attempt)
    messages.success(request, "Your examination session has ended.")
    return redirect("bcl:exam_result", attempt_id=attempt.pk)


@login_required
@require_GET
def exam_result(request, attempt_id):
    attempt = expire_attempt_if_needed(get_candidate_attempt(request, attempt_id))
    if attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
        return redirect("bcl:exam_session", attempt_id=attempt.pk)
    total_marks = sum(
        Question.objects.filter(section__module=attempt.module).values_list("marks", flat=True)
    )
    task_evaluations = (
        list(attempt.task_evaluations.select_related("examiner").order_by("task_number"))
        if attempt.module.module_type == ExamModule.ModuleType.WRITING else []
    )
    return render(request, "exam/result.html", {
        "attempt": attempt,
        "total_marks": total_marks,
        "task_evaluations": task_evaluations,
    })
