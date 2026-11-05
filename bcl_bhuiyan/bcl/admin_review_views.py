"""
Administrative Results & Exam Review Hub
Provides staff and examiners with a centralized, unified dashboard to view, filter,
inspect, and export candidate examination results across Listening, Reading, and Writing,
complete with visible band scores, question-by-question candidate answers alongside official correct answers.
"""
import os
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.utils.http import url_has_allowed_host_and_scheme
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_GET, require_http_methods

from .exam_views import get_listening_review_data
from .models import CandidateAttempt, ExamModule, FullMockAttempt, IELTSMockTest
from .result_exports import get_module_attempt_data


@staff_member_required
@require_GET
def admin_results_hub(request):
    """
    Unified Examiner/Admin Hub: List all student exam submissions (Listening, Reading, Writing, Full Mock)
    with filter tabs, search, visible band scores, raw scores, and direct review links.
    """
    mod_filter = request.GET.get("module", "all").strip().lower()
    search_query = request.GET.get("q", "").strip()
    test_filter = request.GET.get("test", "").strip()

    attempts_qs = (
        CandidateAttempt.objects.exclude(status=CandidateAttempt.AttemptStatus.IN_PROGRESS)
        .select_related("candidate", "module", "module__mock_test", "full_mock")
        .prefetch_related("task_evaluations")
        .order_by("-submitted_at", "-id")
    )

    if search_query:
        attempts_qs = attempts_qs.filter(
            Q(candidate__username__icontains=search_query)
            | Q(candidate__first_name__icontains=search_query)
            | Q(candidate__last_name__icontains=search_query)
            | Q(candidate__email__icontains=search_query)
            | Q(module__mock_test__title__icontains=search_query)
        )

    if test_filter and test_filter.isdigit():
        attempts_qs = attempts_qs.filter(module__mock_test_id=int(test_filter))

    if mod_filter in ("listening", "reading", "writing"):
        attempts_qs = attempts_qs.filter(module__module_type=mod_filter)

    # Global summary metrics for quick overview
    total_completed = CandidateAttempt.objects.exclude(status=CandidateAttempt.AttemptStatus.IN_PROGRESS).count()
    listening_count = CandidateAttempt.objects.filter(module__module_type=ExamModule.ModuleType.LISTENING).exclude(status=CandidateAttempt.AttemptStatus.IN_PROGRESS).count()
    reading_count = CandidateAttempt.objects.filter(module__module_type=ExamModule.ModuleType.READING).exclude(status=CandidateAttempt.AttemptStatus.IN_PROGRESS).count()
    writing_count = CandidateAttempt.objects.filter(module__module_type=ExamModule.ModuleType.WRITING).exclude(status=CandidateAttempt.AttemptStatus.IN_PROGRESS).count()
    full_mock_count = FullMockAttempt.objects.exclude(status=FullMockAttempt.AttemptStatus.IN_PROGRESS).count()

    full_mocks = []
    if mod_filter == "full_mock":
        fm_qs = (
            FullMockAttempt.objects.exclude(status=FullMockAttempt.AttemptStatus.IN_PROGRESS)
            .select_related("candidate", "mock_test", "listening_attempt", "reading_attempt", "writing_attempt")
            .order_by("-submitted_at", "-id")
        )
        if search_query:
            fm_qs = fm_qs.filter(
                Q(candidate__username__icontains=search_query)
                | Q(candidate__first_name__icontains=search_query)
                | Q(candidate__last_name__icontains=search_query)
                | Q(candidate__email__icontains=search_query)
                | Q(mock_test__title__icontains=search_query)
            )
        if test_filter and test_filter.isdigit():
            fm_qs = fm_qs.filter(mock_test_id=int(test_filter))
        full_mocks = fm_qs[:150]

    paginator = Paginator(attempts_qs, 35)
    page_num = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_num)

    mock_tests = IELTSMockTest.objects.all().order_by("test_number")

    return render(request, "admin_tools/results_hub.html", {
        "page_obj": page_obj,
        "attempts": page_obj.object_list,
        "full_mocks": full_mocks,
        "mod_filter": mod_filter,
        "search_query": search_query,
        "test_filter": test_filter,
        "mock_tests": mock_tests,
        "total_completed": total_completed,
        "listening_count": listening_count,
        "reading_count": reading_count,
        "writing_count": writing_count,
        "full_mock_count": full_mock_count,
    })


@staff_member_required
@require_GET
def admin_attempt_review(request, attempt_id):
    """
    Detailed Question-by-Question Review for Admin/Examiner.
    Displays student answers alongside official correct answers, raw score, band score,
    timing details, and continuous audio playback for listening attempts.
    """
    attempt = get_object_or_404(
        CandidateAttempt.objects.select_related("candidate", "module", "module__mock_test", "full_mock"),
        pk=attempt_id
    )

    module = attempt.module
    module_type = module.module_type
    mock_test = module.mock_test

    audio_url = ""
    questions = []
    correct_count = 0
    wrong_count = 0
    writing_tasks = []

    if module_type == ExamModule.ModuleType.LISTENING:
        rev_data = get_listening_review_data(attempt)
        if rev_data:
            questions = rev_data["questions"]
            correct_count = rev_data["correct_count"]
            wrong_count = rev_data["wrong_count"]
            audio_url = rev_data["audio_url"]
    else:
        export_data = get_module_attempt_data(attempt.pk)
        raw_qs = export_data.get("questions_data", [])
        correct_count = export_data.get("correct_count", 0)
        wrong_count = export_data.get("wrong_count", 0)
        writing_tasks = export_data.get("writing_tasks", [])

        # Format questions cleanly for template
        for q in raw_qs:
            ans_val = q.get("candidate_answer", "")
            if ans_val in ("[No Answer]", "None", "null"):
                ans_val = ""
            sec_title = q.get("section_title") or ""
            part_num = 1
            if "2" in sec_title:
                part_num = 2
            elif "3" in sec_title:
                part_num = 3
            elif "4" in sec_title:
                part_num = 4
            questions.append({
                "num": q.get("global_num"),
                "part": part_num,
                "section_title": sec_title,
                "question_text": q.get("question_text"),
                "question_type": q.get("question_type"),
                "user_answer": ans_val,
                "has_answer": bool(ans_val),
                "correct_answer": q.get("correct_answer"),
                "is_correct": bool(q.get("is_correct")),
                "status_class": "correct" if q.get("is_correct") else "incorrect",
                "explanation": q.get("explanation", ""),
            })

    time_taken_str = "00:00"
    if attempt.submitted_at and attempt.started_at:
        sec = max(0, int((attempt.submitted_at - attempt.started_at).total_seconds()))
        time_taken_str = f"{sec // 60:02d}:{sec % 60:02d}"

    return render(request, "admin_tools/attempt_review_detail.html", {
        "attempt": attempt,
        "candidate": attempt.candidate,
        "module": module,
        "mock_test": mock_test,
        "module_type": module_type,
        "questions": questions,
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "total_questions": len(questions),
        "raw_score": attempt.raw_score,
        "band_score": attempt.band_score,
        "writing_tasks": writing_tasks,
        "time_taken": time_taken_str,
        "audio_url": audio_url,
    })


@staff_member_required
@require_GET
def admin_full_mock_review(request, full_attempt_id):
    """
    All-Module Review Inspector for Full Mocks.
    Displays overall band score, plus tabbed access to Listening, Reading, and Writing reviews.
    """
    full_mock = get_object_or_404(
        FullMockAttempt.objects.select_related(
            "candidate", "mock_test",
            "listening_attempt__module", "reading_attempt__module", "writing_attempt__module"
        ),
        pk=full_attempt_id
    )

    listening_review = get_listening_review_data(full_mock.listening_attempt) if full_mock.listening_attempt else None

    reading_data = None
    if full_mock.reading_attempt:
        reading_raw = get_module_attempt_data(full_mock.reading_attempt.pk)
        raw_qs = reading_raw.get("questions_data", [])
        reading_questions = []
        for q in raw_qs:
            ans_val = q.get("candidate_answer", "")
            if ans_val in ("[No Answer]", "None", "null"):
                ans_val = ""
            sec_title = q.get("section_title") or ""
            part_num = 1
            if "2" in sec_title:
                part_num = 2
            elif "3" in sec_title:
                part_num = 3
            elif "4" in sec_title:
                part_num = 4
            reading_questions.append({
                "num": q.get("global_num"),
                "part": part_num,
                "section_title": sec_title,
                "question_text": q.get("question_text"),
                "question_type": q.get("question_type"),
                "user_answer": ans_val,
                "has_answer": bool(ans_val),
                "correct_answer": q.get("correct_answer"),
                "is_correct": bool(q.get("is_correct")),
                "status_class": "correct" if q.get("is_correct") else "incorrect",
                "explanation": q.get("explanation", ""),
            })
        reading_data = {
            "attempt": full_mock.reading_attempt,
            "raw_score": full_mock.reading_attempt.raw_score,
            "band_score": full_mock.reading_attempt.band_score,
            "questions": reading_questions,
            "correct_count": reading_raw.get("correct_count", 0),
            "wrong_count": reading_raw.get("wrong_count", 0),
        }

    writing_data = None
    if full_mock.writing_attempt:
        writing_raw = get_module_attempt_data(full_mock.writing_attempt.pk)
        writing_data = {
            "attempt": full_mock.writing_attempt,
            "band_score": full_mock.writing_attempt.band_score,
            "writing_tasks": writing_raw.get("writing_tasks", []),
        }

    return render(request, "admin_tools/full_mock_review_detail.html", {
        "full_mock": full_mock,
        "candidate": full_mock.candidate,
        "mock_test": full_mock.mock_test,
        "listening_review": listening_review,
        "reading_data": reading_data,
        "writing_data": writing_data,
    })


@staff_member_required
@require_http_methods(["POST"])
def admin_attempt_delete(request, attempt_id):
    """
    Delete a candidate module attempt (Writing, Listening, or Reading) along with all
    associated answers and evaluations to keep database storage clean.
    """
    attempt = get_object_or_404(
        CandidateAttempt.objects.select_related("candidate", "module", "module__mock_test", "full_mock"),
        pk=attempt_id,
    )
    mod_name = attempt.module.get_module_type_display() if attempt.module else "Exam"
    candidate_name = attempt.candidate.get_full_name() or attempt.candidate.username
    mock_title = attempt.module.mock_test.title if attempt.module and attempt.module.mock_test else f"Attempt #{attempt.pk}"

    with transaction.atomic():
        if attempt.full_mock:
            fm = attempt.full_mock
            if attempt.module and attempt.module.module_type == ExamModule.ModuleType.WRITING:
                fm.writing_attempt = None
            elif attempt.module and attempt.module.module_type == ExamModule.ModuleType.READING:
                fm.reading_attempt = None
            elif attempt.module and attempt.module.module_type == ExamModule.ModuleType.LISTENING:
                fm.listening_attempt = None
            fm.calculate_overall_score()
            fm.save()

        attempt.delete()

    messages.success(
        request,
        f"{mod_name} submission #{attempt_id} ({candidate_name} — {mock_title}) and all submitted answers were permanently deleted."
    )

    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("bcl:admin_results_hub")
