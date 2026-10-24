from datetime import timedelta
import json
import logging
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import CandidateAnswer, CandidateAttempt, ExamModule, Question, FullMockAttempt, IELTSMockTest
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
        # Lock in the same order as start/save/violation/submit endpoints:
        # candidate first, then attempt. This serializes timer-triggered expiry
        # with answer submission and session creation on PostgreSQL.
        get_user_model().objects.select_for_update().get(pk=attempt.candidate_id)
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
        if attempt.full_mock_id:
            return redirect("bcl:full_mock_ended", full_attempt_id=attempt.full_mock_id)
        return redirect("bcl:exam_ended", attempt_id=attempt.pk)
    # An older duplicate must not display an active exam interface.
    if is_superseded_active_attempt(attempt):
        return redirect("bcl:exam_rules", module_id=attempt.module_id)

    sections = attempt.module.sections.order_by("order", "pk").prefetch_related("questions__options")
    saved_answers = list(
        CandidateAnswer.objects.filter(attempt=attempt).values(
            "question_id", "answer_text", "is_flagged"
        )
    )
    module_audio_url = ""
    audio_file = getattr(attempt.module, "audio_file", None)
    if audio_file and audio_file.name:
        try:
            if audio_file.storage.exists(audio_file.name):
                from django.urls import reverse
                module_audio_url = reverse("bcl:module_media", args=[attempt.pk, "audio"])
        except Exception:
            pass

    return render(request, "exam/session.html", {
        "attempt": attempt,
        "module": attempt.module,
        "mock_test": attempt.module.mock_test,
        "sections": sections,
        "remaining_seconds": get_remaining_seconds(attempt),
        "saved_answers": saved_answers,
        "module_audio_url": module_audio_url,
    })


@login_required
@require_GET
def exam_timer(request, attempt_id):
    attempt = expire_attempt_if_needed(get_candidate_attempt(request, attempt_id))
    if (attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS
            and is_superseded_active_attempt(attempt)):
        return JsonResponse({
            "error": "This session was superseded by a newer active session.",
            "attempt_id": attempt.pk,
            "status": "superseded",
            "remaining_seconds": 0,
        }, status=409)
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
        if question.question_type == Question.QuestionType.MULTI_SELECT and value:
            valid_keys = {option.option_key for option in question.options.all()}
            selected_keys = [k.strip() for k in value.split(";;;") if k.strip()]
            if not selected_keys or any(k not in valid_keys for k in selected_keys):
                return JsonResponse({"error": "Invalid multi-select selection."}, status=400)
        if question.question_type == Question.QuestionType.MAP_LABELLING and value:
            valid_keys = {option.option_key for option in question.options.all()}
            if valid_keys and value not in valid_keys:
                return JsonResponse({"error": "Invalid map label selection."}, status=400)
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

        max_violations = getattr(settings, "MAX_EXAM_VIOLATIONS", 3)
        attempt.violation_count += 1
        is_auto_submitted = False
        if attempt.violation_count >= max_violations:
            attempt.status = CandidateAttempt.AttemptStatus.AUTO_SUBMITTED
            attempt.submitted_at = now
            attempt.save(update_fields=["violation_count", "status", "submitted_at"])
            finalize_attempt_score(attempt)
            is_auto_submitted = True
            if attempt.full_mock_id:
                try:
                    full_mock = FullMockAttempt.objects.select_for_update().get(pk=attempt.full_mock_id)
                    full_mock.status = attempt.status
                    full_mock.current_step = "completed"
                    full_mock.submitted_at = now
                    full_mock.calculate_overall_score()
                    full_mock.save()
                except Exception:
                    pass
        else:
            attempt.save(update_fields=["violation_count"])
        count = attempt.violation_count
        status = attempt.status
        logger.warning(
            "Exam focus-loss report: attempt_id=%s candidate_id=%s reason=%s count=%s status=%s",
            attempt.pk, request.user.pk, reason, count, status,
        )

    redirect_url = None
    if is_auto_submitted:
        if attempt.full_mock_id:
            redirect_url = reverse("bcl:full_mock_ended", args=[attempt.full_mock_id])
        else:
            redirect_url = reverse("bcl:exam_ended", args=[attempt.pk])

    if is_auto_submitted:
        warning_title = "Exam Auto-Submitted"
        warning_msg = "Your exam has been automatically submitted due to repeated tab switching violations."
    elif count == 1:
        warning_title = f"Exam Integrity Warning (1 of {max_violations - 1})"
        warning_msg = (
            f"First warning (1 of {max_violations - 1}): You left the examination tab or window. "
            f"Switching tabs a total of {max_violations} times will automatically submit your exam."
        )
    else:
        warning_title = f"Final Exam Integrity Warning ({count} of {max_violations - 1})"
        warning_msg = (
            f"Final warning ({count} of {max_violations - 1}): You left the examination tab again. "
            f"Switching tabs one more time will automatically submit and end your exam immediately!"
        )

    return JsonResponse({
        "violation_count": count,
        "max_violations": max_violations,
        "status": status,
        "warning": (count < max_violations and not is_auto_submitted),
        "warning_title": warning_title,
        "warning_message": warning_msg,
        "auto_submitted": is_auto_submitted,
        "redirect_url": redirect_url,
    })


@login_required
@require_POST
def submit_exam(request, attempt_id):
    if not is_candidate(request.user):
        return JsonResponse({"error": "Candidates only."}, status=403)
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        attempt = get_object_or_404(
            CandidateAttempt.objects.select_for_update().select_related("module"),
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

        if attempt.full_mock_id:
            full_mock = FullMockAttempt.objects.select_for_update().get(pk=attempt.full_mock_id)
            is_exit = request.POST.get("exit_full_mock") == "true"

            if is_exit or attempt.module.module_type == ExamModule.ModuleType.WRITING:
                full_mock.status = attempt.status
                full_mock.current_step = "completed"
                full_mock.submitted_at = timezone.now()
                full_mock.calculate_overall_score()
                full_mock.save()
                messages.success(request, "Your All-Module examination session has ended.")
                return redirect("bcl:full_mock_ended", full_attempt_id=full_mock.pk)
            elif attempt.module.module_type == ExamModule.ModuleType.READING:
                full_mock.current_step = "listening"
                full_mock.save(update_fields=["current_step"])
                messages.success(request, "Reading module completed. Next stage: Listening.")
                return redirect("bcl:full_mock_intermission", full_attempt_id=full_mock.pk)
            elif attempt.module.module_type == ExamModule.ModuleType.LISTENING:
                full_mock.current_step = "writing"
                full_mock.save(update_fields=["current_step"])
                messages.success(request, "Listening module completed. Next stage: Writing.")
                return redirect("bcl:full_mock_intermission", full_attempt_id=full_mock.pk)

    messages.success(request, "Your examination session has ended.")
    return redirect("bcl:exam_ended", attempt_id=attempt.pk)


@login_required
@require_GET
def exam_ended(request, attempt_id):
    attempt = expire_attempt_if_needed(get_candidate_attempt(request, attempt_id))
    if attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
        return redirect("bcl:exam_session", attempt_id=attempt.pk)

    return render(request, "exam/ended.html", {
        "attempt": attempt,
        "module": attempt.module,
        "mock_test": attempt.module.mock_test,
    })


@login_required
@require_GET
def exam_result(request, attempt_id):
    if request.user.is_staff or request.user.is_superuser:
        attempt = get_object_or_404(
            CandidateAttempt.objects.select_related("module", "module__mock_test", "candidate"),
            pk=attempt_id,
        )
    else:
        attempt = get_candidate_attempt(request, attempt_id)
    attempt = expire_attempt_if_needed(attempt)
    if attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS and not (request.user.is_staff or request.user.is_superuser):
        return redirect("bcl:exam_session", attempt_id=attempt.pk)

    module = attempt.module
    mock_test = module.mock_test
    module_type = module.module_type

    time_taken_str = "00:00"
    if attempt.submitted_at and attempt.started_at:
        seconds = max(0, int((attempt.submitted_at - attempt.started_at).total_seconds()))
        m = seconds // 60
        s = seconds % 60
        time_taken_str = f"{m:02d}:{s:02d}"

    task_evaluations = (
        list(attempt.task_evaluations.select_related("examiner", "question").order_by("task_number"))
        if module_type == ExamModule.ModuleType.WRITING else []
    )

    if module_type == ExamModule.ModuleType.WRITING:
        total_marks = sum(
            Question.objects.filter(section__module=module).values_list("marks", flat=True)
        )
        sections = list(module.sections.order_by("order", "pk").prefetch_related("questions"))
        answers = {
            a.question_id: a for a in CandidateAnswer.objects.filter(attempt=attempt)
        }
        sections_data = []
        for section in sections:
            questions_data = []
            for q in section.questions.order_by("order"):
                ans = answers.get(q.pk)
                ans_text = ans.answer_text if ans else ""
                words = len(ans_text.strip().split()) if ans_text.strip() else 0
                questions_data.append({
                    "question": q,
                    "answer_text": ans_text,
                    "word_count": words,
                })
            sections_data.append({
                "section": section,
                "questions": questions_data,
            })
        return render(request, "exam/result.html", {
            "attempt": attempt,
            "module": module,
            "mock_test": mock_test,
            "module_type": module_type,
            "time_taken": time_taken_str,
            "total_marks": total_marks,
            "task_evaluations": task_evaluations,
            "sections_data": sections_data,
            "is_evaluated": len(task_evaluations) == 2,
        })

    # Objective: Reading or Listening
    sections = list(module.sections.order_by("order", "pk").prefetch_related("questions__options"))
    answers = {
        a.question_id: a for a in CandidateAnswer.objects.filter(attempt=attempt)
    }

    correct_count = 0
    wrong_count = 0
    global_counter = 1
    sections_data = []

    for section in sections:
        sec_correct = 0
        sec_total = 0
        questions_data = []
        for q in section.questions.order_by("order", "pk"):
            ans = answers.get(q.pk)
            candidate_answer = ans.answer_text if ans else ""
            is_correct = bool(ans and ans.is_correct)
            is_blank = not bool(candidate_answer.strip())

            if is_correct:
                correct_count += 1
                sec_correct += 1
            else:
                wrong_count += 1
            sec_total += 1

            questions_data.append({
                "question": q,
                "global_num": global_counter,
                "candidate_answer": candidate_answer,
                "is_correct": is_correct,
                "is_blank": is_blank,
                "explanation": q.explanation,
                "options": list(q.options.order_by("order", "option_key")),
            })
            blank_step = 1
            if q.question_type == Question.QuestionType.FILL_BLANK:
                import re
                p_count = len(re.findall(r"_{3,}", q.question_text))
                a_count = len([x for x in q.correct_answer.split(";;;") if x.strip()])
                blank_step = max(p_count, a_count, q.answer_count or 1, 1)
            global_counter += blank_step

        sections_data.append({
            "section": section,
            "correct_count": sec_correct,
            "total_count": sec_total,
            "questions": questions_data,
        })

    total_marks = correct_count + wrong_count

    review_module_audio_url = ""
    audio_file = getattr(module, "audio_file", None)
    if audio_file and audio_file.name:
        try:
            if audio_file.storage.exists(audio_file.name):
                from django.urls import reverse
                review_module_audio_url = reverse("bcl:review_module_media", args=[attempt.pk, "audio"])
        except Exception:
            pass

    return render(request, "exam/result.html", {
        "attempt": attempt,
        "module": module,
        "mock_test": mock_test,
        "module_type": module_type,
        "time_taken": time_taken_str,
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "total_marks": total_marks,
        "task_evaluations": task_evaluations,
        "sections_data": sections_data,
        "review_module_audio_url": review_module_audio_url,
    })


# ==========================================
# ALL MODULES (FULL MOCK) VIEWS
# ==========================================

@login_required
@require_GET
def full_mock_rules(request, mock_test_id):
    if not is_candidate(request.user):
        messages.error(request, "Administrator accounts cannot take candidate examinations.")
        return redirect("bcl:dashboard")

    mock_test = get_object_or_404(
        IELTSMockTest.objects.prefetch_related("modules"),
        pk=mock_test_id,
        is_published=True,
    )
    if not mock_test.has_all_modules:
        messages.error(request, "This mock test does not have all three modules (Reading, Listening, Writing) configured.")
        return redirect("bcl:dashboard")

    active_full = (
        FullMockAttempt.objects
        .filter(candidate=request.user, mock_test=mock_test, status=FullMockAttempt.AttemptStatus.IN_PROGRESS)
        .order_by("-started_at")
        .first()
    )
    if active_full:
        if active_full.current_step == "reading" and active_full.reading_attempt:
            att = expire_attempt_if_needed(active_full.reading_attempt)
            if att.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
                return redirect("bcl:exam_session", attempt_id=att.pk)
            else:
                active_full.current_step = "listening"
                active_full.save(update_fields=["current_step"])
                return redirect("bcl:full_mock_intermission", full_attempt_id=active_full.pk)

        elif active_full.current_step == "listening" and active_full.listening_attempt:
            att = expire_attempt_if_needed(active_full.listening_attempt)
            if att.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
                return redirect("bcl:exam_session", attempt_id=att.pk)
            else:
                active_full.current_step = "writing"
                active_full.save(update_fields=["current_step"])
                return redirect("bcl:full_mock_intermission", full_attempt_id=active_full.pk)

        elif active_full.current_step == "writing" and active_full.writing_attempt:
            att = expire_attempt_if_needed(active_full.writing_attempt)
            if att.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
                return redirect("bcl:exam_session", attempt_id=att.pk)
            else:
                active_full.status = att.status
                active_full.current_step = "completed"
                active_full.submitted_at = timezone.now()
                active_full.calculate_overall_score()
                active_full.save()
                return redirect("bcl:full_mock_ended", full_attempt_id=active_full.pk)

        elif active_full.current_step in {"listening", "writing"}:
            return redirect("bcl:full_mock_intermission", full_attempt_id=active_full.pk)
        elif active_full.current_step == "completed":
            return redirect("bcl:full_mock_ended", full_attempt_id=active_full.pk)

    modules_by_type = {m.module_type: m for m in mock_test.modules.filter(is_active=True)}
    return render(request, "exam/full_mock_rules.html", {
        "mock_test": mock_test,
        "reading_module": modules_by_type.get("reading"),
        "listening_module": modules_by_type.get("listening"),
        "writing_module": modules_by_type.get("writing"),
        "total_duration": mock_test.all_modules_duration_minutes,
    })


@login_required
@require_POST
def start_full_mock(request, mock_test_id):
    if not is_candidate(request.user):
        messages.error(request, "This action is only available to candidates.")
        return redirect("bcl:dashboard")
    if request.POST.get("accept_rules") != "yes":
        messages.error(request, "You must accept the examination rules before starting.")
        return redirect("bcl:full_mock_rules", mock_test_id=mock_test_id)

    mock_test = get_object_or_404(
        IELTSMockTest.objects.prefetch_related("modules"),
        pk=mock_test_id,
        is_published=True,
    )
    if not mock_test.has_all_modules:
        messages.error(request, "This mock test does not have all three modules configured.")
        return redirect("bcl:dashboard")

    reading_module = mock_test.modules.get(module_type=ExamModule.ModuleType.READING, is_active=True)

    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        now = timezone.now()

        active_full = (
            FullMockAttempt.objects.select_for_update()
            .filter(candidate=request.user, mock_test=mock_test, status=FullMockAttempt.AttemptStatus.IN_PROGRESS)
            .order_by("-started_at")
            .first()
        )
        if not active_full:
            active_full = FullMockAttempt.objects.create(
                candidate=request.user,
                mock_test=mock_test,
                status=FullMockAttempt.AttemptStatus.IN_PROGRESS,
                current_step="reading",
                started_at=now,
            )

        if not active_full.reading_attempt:
            reading_attempt = CandidateAttempt.objects.create(
                candidate=request.user,
                module=reading_module,
                full_mock=active_full,
                started_at=now,
                expires_at=now + timedelta(minutes=reading_module.duration_minutes),
                status=CandidateAttempt.AttemptStatus.IN_PROGRESS,
            )
            active_full.reading_attempt = reading_attempt
            active_full.save(update_fields=["reading_attempt"])
        else:
            reading_attempt = expire_attempt_if_needed(active_full.reading_attempt)
            if reading_attempt.status != CandidateAttempt.AttemptStatus.IN_PROGRESS:
                active_full.current_step = "listening"
                active_full.save(update_fields=["current_step"])
                return redirect("bcl:full_mock_intermission", full_attempt_id=active_full.pk)

    return redirect("bcl:exam_session", attempt_id=active_full.reading_attempt.pk)


@login_required
@require_GET
def full_mock_intermission(request, full_attempt_id):
    if not is_candidate(request.user):
        messages.error(request, "Candidates only.")
        return redirect("bcl:dashboard")

    full_mock = get_object_or_404(
        FullMockAttempt.objects.select_related("mock_test", "reading_attempt", "listening_attempt", "writing_attempt"),
        pk=full_attempt_id,
        candidate=request.user,
    )
    if full_mock.status != FullMockAttempt.AttemptStatus.IN_PROGRESS or full_mock.current_step == "completed":
        return redirect("bcl:full_mock_ended", full_attempt_id=full_mock.pk)

    step_info = {}
    if full_mock.current_step == "listening":
        step_info = {
            "completed_module_name": "Reading",
            "completed_attempt": full_mock.reading_attempt,
            "next_module_name": "Listening",
            "next_module_type": "listening",
            "next_duration": 30,
            "stage_number": 2,
            "total_stages": 3,
            "tips": [
                "Ensure your audio device or headphones are working clearly.",
                "Listening audio will play continuously and cannot be paused once started.",
                "The listening test consists of 4 parts and 40 questions in total.",
            ],
        }
    elif full_mock.current_step == "writing":
        step_info = {
            "completed_module_name": "Listening",
            "completed_attempt": full_mock.listening_attempt,
            "next_module_name": "Writing",
            "next_module_type": "writing",
            "next_duration": 60,
            "stage_number": 3,
            "total_stages": 3,
            "tips": [
                "Writing consists of Task 1 (recommended 20 mins, min 150 words) and Task 2 (recommended 40 mins, min 250 words).",
                "Your responses are autosaved regularly while you type.",
                "Writing will be submitted for manual review by certified examiners upon completion.",
            ],
        }
    else:
        if full_mock.reading_attempt:
            return redirect("bcl:exam_session", attempt_id=full_mock.reading_attempt.pk)
        return redirect("bcl:full_mock_rules", mock_test_id=full_mock.mock_test_id)

    return render(request, "exam/full_mock_intermission.html", {
        "full_mock": full_mock,
        "mock_test": full_mock.mock_test,
        "step_info": step_info,
    })


@login_required
@require_POST
def full_mock_next_module(request, full_attempt_id):
    if not is_candidate(request.user):
        messages.error(request, "Candidates only.")
        return redirect("bcl:dashboard")

    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        full_mock = get_object_or_404(
            FullMockAttempt.objects.select_for_update().select_related("mock_test"),
            pk=full_attempt_id,
            candidate=request.user,
        )
        if full_mock.status != FullMockAttempt.AttemptStatus.IN_PROGRESS:
            return redirect("bcl:full_mock_ended", full_attempt_id=full_mock.pk)

        now = timezone.now()
        if full_mock.current_step == "listening":
            listening_mod = full_mock.mock_test.modules.get(module_type=ExamModule.ModuleType.LISTENING, is_active=True)
            if not full_mock.listening_attempt:
                listening_att = CandidateAttempt.objects.create(
                    candidate=request.user,
                    module=listening_mod,
                    full_mock=full_mock,
                    started_at=now,
                    expires_at=now + timedelta(minutes=listening_mod.duration_minutes),
                    status=CandidateAttempt.AttemptStatus.IN_PROGRESS,
                )
                full_mock.listening_attempt = listening_att
                full_mock.save(update_fields=["listening_attempt"])
            else:
                listening_att = expire_attempt_if_needed(full_mock.listening_attempt)
                if listening_att.status != CandidateAttempt.AttemptStatus.IN_PROGRESS:
                    full_mock.current_step = "writing"
                    full_mock.save(update_fields=["current_step"])
                    return redirect("bcl:full_mock_intermission", full_attempt_id=full_mock.pk)
            return redirect("bcl:exam_session", attempt_id=full_mock.listening_attempt.pk)

        elif full_mock.current_step == "writing":
            writing_mod = full_mock.mock_test.modules.get(module_type=ExamModule.ModuleType.WRITING, is_active=True)
            if not full_mock.writing_attempt:
                writing_att = CandidateAttempt.objects.create(
                    candidate=request.user,
                    module=writing_mod,
                    full_mock=full_mock,
                    started_at=now,
                    expires_at=now + timedelta(minutes=writing_mod.duration_minutes),
                    status=CandidateAttempt.AttemptStatus.IN_PROGRESS,
                )
                full_mock.writing_attempt = writing_att
                full_mock.save(update_fields=["writing_attempt"])
            else:
                writing_att = expire_attempt_if_needed(full_mock.writing_attempt)
                if writing_att.status != CandidateAttempt.AttemptStatus.IN_PROGRESS:
                    full_mock.status = writing_att.status
                    full_mock.current_step = "completed"
                    full_mock.submitted_at = now
                    full_mock.calculate_overall_score()
                    full_mock.save()
                    return redirect("bcl:full_mock_ended", full_attempt_id=full_mock.pk)
            return redirect("bcl:exam_session", attempt_id=full_mock.writing_attempt.pk)

        else:
            return redirect("bcl:full_mock_ended", full_attempt_id=full_mock.pk)


@login_required
@require_GET
def full_mock_ended(request, full_attempt_id):
    if not is_candidate(request.user):
        messages.error(request, "Candidates only.")
        return redirect("bcl:dashboard")

    full_mock = get_object_or_404(
        FullMockAttempt.objects.select_related("mock_test", "reading_attempt", "listening_attempt", "writing_attempt"),
        pk=full_attempt_id,
        candidate=request.user,
    )
    if full_mock.status == FullMockAttempt.AttemptStatus.IN_PROGRESS:
        if full_mock.current_step in {"listening", "writing"} and not getattr(full_mock, f"{full_mock.current_step}_attempt"):
            return redirect("bcl:full_mock_intermission", full_attempt_id=full_mock.pk)
        active_att = getattr(full_mock, f"{full_mock.current_step}_attempt", None)
        if active_att:
            return redirect("bcl:exam_session", attempt_id=active_att.pk)

    return render(request, "exam/full_mock_ended.html", {
        "full_mock": full_mock,
        "mock_test": full_mock.mock_test,
    })


@login_required
@require_GET
def full_mock_result(request, full_attempt_id):
    if not (is_candidate(request.user) or request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Access denied.")
        return redirect("bcl:dashboard")

    qs = FullMockAttempt.objects.select_related(
        "mock_test",
        "reading_attempt__module",
        "listening_attempt__module",
        "writing_attempt__module",
        "candidate",
    ).prefetch_related(
        "writing_attempt__task_evaluations__examiner",
        "writing_attempt__task_evaluations__question",
    )
    if not (request.user.is_staff or request.user.is_superuser):
        qs = qs.filter(candidate=request.user)

    full_mock = get_object_or_404(qs, pk=full_attempt_id)
    if full_mock.status == FullMockAttempt.AttemptStatus.IN_PROGRESS and not (request.user.is_staff or request.user.is_superuser):
        return redirect("bcl:full_mock_rules", mock_test_id=full_mock.mock_test_id)

    writing_att = full_mock.writing_attempt
    writing_evaluations = list(writing_att.task_evaluations.all().order_by("task_number")) if writing_att else []
    is_writing_evaluated = bool(writing_att and len(writing_evaluations) == 2 and writing_att.band_score is not None)

    if is_writing_evaluated:
        full_mock.calculate_overall_score()
        full_mock.save(update_fields=["overall_band_score"])

    writing_tasks = []
    if writing_att:
        sections = list(writing_att.module.sections.order_by("order", "pk").prefetch_related("questions"))
        ans_map = {a.question_id: a for a in CandidateAnswer.objects.filter(attempt=writing_att)}
        eval_map = {ev.task_number: ev for ev in writing_evaluations}
        task_num = 1
        for sec in sections:
            for q in sec.questions.order_by("order"):
                user_ans = ans_map.get(q.pk)
                ans_text = user_ans.answer_text if user_ans else ""
                words = len(ans_text.strip().split()) if ans_text.strip() else 0
                evaluation = eval_map.get(task_num)
                writing_tasks.append({
                    "task_number": task_num,
                    "section": sec,
                    "question": q,
                    "answer_text": ans_text,
                    "word_count": words,
                    "evaluation": evaluation,
                })
                task_num += 1

    reading_time = "00:00"
    if full_mock.reading_attempt and full_mock.reading_attempt.submitted_at:
        sec = max(0, int((full_mock.reading_attempt.submitted_at - full_mock.reading_attempt.started_at).total_seconds()))
        reading_time = f"{sec // 60:02d}:{sec % 60:02d}"

    listening_time = "00:00"
    if full_mock.listening_attempt and full_mock.listening_attempt.submitted_at:
        sec = max(0, int((full_mock.listening_attempt.submitted_at - full_mock.listening_attempt.started_at).total_seconds()))
        listening_time = f"{sec // 60:02d}:{sec % 60:02d}"

    writing_time = "00:00"
    if full_mock.writing_attempt and full_mock.writing_attempt.submitted_at:
        sec = max(0, int((full_mock.writing_attempt.submitted_at - full_mock.writing_attempt.started_at).total_seconds()))
        writing_time = f"{sec // 60:02d}:{sec % 60:02d}"

    return render(request, "exam/full_mock_result.html", {
        "full_mock": full_mock,
        "mock_test": full_mock.mock_test,
        "reading_attempt": full_mock.reading_attempt,
        "listening_attempt": full_mock.listening_attempt,
        "writing_attempt": full_mock.writing_attempt,
        "reading_time": reading_time,
        "listening_time": listening_time,
        "writing_time": writing_time,
        "is_writing_evaluated": is_writing_evaluated,
        "writing_evaluations": writing_evaluations,
        "writing_tasks": writing_tasks,
        "overall_band": full_mock.overall_band_score if is_writing_evaluated else None,
    })
