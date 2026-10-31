import json
import logging
from decimal import Decimal
from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .guards import full_mock_sequence_guard, attempt_ownership_guard
from .models import (
    CandidateAnswer,
    CandidateAttempt,
    ExamModule,
    ExamSection,
    FullMockAttempt,
    IELTSMockTest,
    Question,
)
from .scoring import band_for_raw
from .exam_views import (
    expire_attempt_if_needed,
    get_mock_test_object,
    is_candidate,
    parse_listening_answer_key,
    render_listening_html,
    exam_session,
    submit_exam,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# MODE B: FULL MOCK TEST SEQUENTIAL SSR ORCHESTRATION
# ==============================================================================

@login_required
@require_POST
def full_mock_start(request, mock_id):
    """
    POST /mock/<mock_id>/start/
    Initiates the FullMockAttempt and redirects to Stage 1: Listening.
    """
    if not is_candidate(request.user):
        messages.error(request, "Candidates only.")
        return redirect("bcl:dashboard")

    mock_test = get_mock_test_object(mock_id)
    if not mock_test:
        raise Http404(f"Mock test {mock_id} not found.")

    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        now = timezone.now()
        full_mock = (
            FullMockAttempt.objects.select_for_update()
            .filter(candidate=request.user, mock_test=mock_test, status=FullMockAttempt.AttemptStatus.IN_PROGRESS)
            .order_by("-started_at")
            .first()
        )
        if not full_mock:
            full_mock = FullMockAttempt.objects.create(
                candidate=request.user,
                mock_test=mock_test,
                status=FullMockAttempt.AttemptStatus.IN_PROGRESS,
                current_step="listening",
                started_at=now,
            )

    return redirect(f"/mock/{mock_test.test_number}/listening/")


# --- STAGE 1: LISTENING ---

@login_required
@require_GET
def full_mock_listening_view(request, mock_id):
    """
    GET /mock/<id>/listening/
    Renders raw static HTML for listening with audio playback and client timer,
    wrapped in server-authoritative context with sequence enforcement.
    """
    if not is_candidate(request.user):
        messages.error(request, "Candidates only.")
        return redirect("bcl:dashboard")

    mock_test = get_mock_test_object(mock_id)
    if not mock_test:
        raise Http404(f"Mock test {mock_id} not found.")

    listening_mod = get_object_or_404(
        ExamModule, mock_test=mock_test, module_type=ExamModule.ModuleType.LISTENING, is_active=True
    )

    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        now = timezone.now()

        # Check full mock session progress
        full_mock = (
            FullMockAttempt.objects.select_for_update()
            .filter(candidate=request.user, mock_test=mock_test, status=FullMockAttempt.AttemptStatus.IN_PROGRESS)
            .order_by("-started_at")
            .first()
        )

        if full_mock:
            # Enforce sequence: if listening is already finished, do not re-take, route forward
            if full_mock.current_step == "listening_done":
                return redirect(f"/mock/{mock_test.test_number}/listening/complete/")
            elif full_mock.current_step == "reading":
                return redirect(f"/mock/{mock_test.test_number}/reading/")
            elif full_mock.current_step == "reading_done":
                return redirect(f"/mock/{mock_test.test_number}/reading/complete/")
            elif full_mock.current_step == "writing":
                return redirect(f"/mock/{mock_test.test_number}/writing/")
            elif full_mock.current_step == "completed":
                return redirect(f"/mock/{mock_test.test_number}/consolidated-result/")

            if not full_mock.listening_attempt:
                attempt = CandidateAttempt.objects.create(
                    candidate=request.user,
                    module=listening_mod,
                    full_mock=full_mock,
                    started_at=now,
                    expires_at=now + timedelta(minutes=listening_mod.duration_minutes),
                    status=CandidateAttempt.AttemptStatus.IN_PROGRESS,
                )
                full_mock.listening_attempt = attempt
                full_mock.save(update_fields=["listening_attempt"])
            else:
                attempt = expire_attempt_if_needed(full_mock.listening_attempt)
                if attempt.status != CandidateAttempt.AttemptStatus.IN_PROGRESS:
                    full_mock.current_step = "listening_done"
                    full_mock.save(update_fields=["current_step"])
                    return redirect(f"/mock/{mock_test.test_number}/listening/complete/")
        else:
            # Standalone Individual Listening practice
            attempt = (
                CandidateAttempt.objects.select_for_update()
                .filter(candidate=request.user, module=listening_mod, status=CandidateAttempt.AttemptStatus.IN_PROGRESS)
                .order_by("-started_at")
                .first()
            )
            if attempt:
                attempt = expire_attempt_if_needed(attempt)
            if not attempt or attempt.status != CandidateAttempt.AttemptStatus.IN_PROGRESS:
                attempt = CandidateAttempt.objects.create(
                    candidate=request.user,
                    module=listening_mod,
                    full_mock=None,
                    started_at=now,
                    expires_at=now + timedelta(minutes=listening_mod.duration_minutes),
                    status=CandidateAttempt.AttemptStatus.IN_PROGRESS,
                )

    return render_listening_html(request, attempt)


@login_required
@require_POST
def full_mock_listening_submit(request, mock_id):
    """
    POST /mock/<id>/listening/submit/ or POST /mock/<attempt_id>/listening/submit/
    Single traditional HTML Form POST sending all answers at once to the backend.
    Saves listening answers, computes score/band, and 302 redirects to:
      - Full Mock: /mock/<id>/listening/complete/
      - Standalone: /result/<attempt_id>/
    """
    if not is_candidate(request.user):
        messages.error(request, "Candidates only.")
        return redirect("bcl:dashboard")

    # Resolve attempt: mock_id might be mock_test.test_number or attempt_id
    attempt = None
    mock_test = get_mock_test_object(mock_id)
    if mock_test:
        listening_mod = ExamModule.objects.filter(mock_test=mock_test, module_type=ExamModule.ModuleType.LISTENING).first()
        if listening_mod:
            attempt = (
                CandidateAttempt.objects.filter(candidate=request.user, module=listening_mod, status=CandidateAttempt.AttemptStatus.IN_PROGRESS)
                .order_by("-started_at")
                .first()
            )
    if not attempt:
        # Check if mock_id is attempt.pk
        attempt = CandidateAttempt.objects.filter(pk=mock_id, candidate=request.user).first()

    if not attempt:
        # Check if already submitted
        completed_attempt = CandidateAttempt.objects.filter(
            candidate=request.user, module__module_type=ExamModule.ModuleType.LISTENING
        ).order_by("-started_at").first()
        if completed_attempt and completed_attempt.full_mock:
            return redirect(f"/mock/{completed_attempt.module.mock_test.test_number}/listening/complete/")
        elif completed_attempt:
            return redirect(f"/result/{completed_attempt.pk}/")
        return redirect("bcl:dashboard")

    test_number = attempt.module.mock_test.test_number

    # Process Form POST answers
    raw_score_val = request.POST.get("raw_score")
    band_score_val = request.POST.get("band_score")
    answers_payload_raw = request.POST.get("answers_payload") or request.POST.get("answers") or request.POST.get("answers_json")

    score = None
    if raw_score_val is not None:
        try:
            score = int(raw_score_val)
        except (ValueError, TypeError):
            pass

    answers_dict = {}
    if answers_payload_raw:
        try:
            if isinstance(answers_payload_raw, str):
                payload_data = json.loads(answers_payload_raw)
            else:
                payload_data = answers_payload_raw
            if isinstance(payload_data, dict):
                answers_dict = payload_data.get("answers", payload_data)
        except Exception as exc:
            logger.warning("Could not parse answers payload: %s", exc)

    # Server answer key authoritative verification if score is missing
    server_keys = parse_listening_answer_key(test_number)
    if score is None:
        eval_score = 0
        for i in range(1, 41):
            k = str(i)
            item = answers_dict.get(k)
            u_ans = ""
            if isinstance(item, dict):
                u_ans = str(item.get("user_answer", "")).strip()
            elif isinstance(item, str):
                u_ans = item.strip()
            
            c_key = server_keys.get(k, "")
            is_cor = False
            if isinstance(c_key, (list, tuple)):
                is_cor = u_ans.lower() in [str(x).strip().lower() for x in c_key]
            elif isinstance(c_key, str) and "," in c_key:
                synonyms = [s.strip().lower() for s in c_key.split(",") if s.strip()]
                is_cor = u_ans.lower() in synonyms or u_ans.lower() == c_key.strip().lower()
            elif c_key:
                is_cor = (u_ans.lower() == str(c_key).strip().lower())

            if is_cor:
                eval_score += 1
        score = eval_score

    band = Decimal(str(band_for_raw(ExamModule.ModuleType.LISTENING, score)))

    with transaction.atomic():
        now = timezone.now()
        attempt.raw_score = score
        attempt.band_score = band
        attempt.status = CandidateAttempt.AttemptStatus.SUBMITTED
        attempt.submitted_at = now
        if answers_dict:
            attempt.answers_payload = {
                "score": score,
                "total": 40,
                "band_score": str(band),
                "answers": answers_dict,
            }
        attempt.save(update_fields=["raw_score", "band_score", "status", "submitted_at", "answers_payload"])

        if attempt.full_mock:
            full_mock = attempt.full_mock
            full_mock.current_step = "listening_done"
            full_mock.save(update_fields=["current_step"])
            return redirect(f"/mock/{test_number}/listening/complete/")

    return redirect(f"/result/{attempt.pk}/")


@login_required
@require_GET
def full_mock_listening_complete(request, mock_id):
    """
    GET /mock/<id>/listening/complete/
    SSR Interstitial showing:
    - Listening: Green (Completed)
    - Reading: Blue (Pending)
    - Writing: Blue (Pending)
    Actions:
    - "View Current Result" (GET /exam/session/<id>/result/)
    - "Go to Next Module" (Form POST to /mock/<id>/reading/)
    """
    if not is_candidate(request.user):
        messages.error(request, "Candidates only.")
        return redirect("bcl:dashboard")

    mock_test = get_mock_test_object(mock_id)
    if not mock_test:
        raise Http404(f"Mock test {mock_id} not found.")

    full_mock = (
        FullMockAttempt.objects.filter(candidate=request.user, mock_test=mock_test)
        .order_by("-started_at")
        .first()
    )
    if not full_mock:
        return redirect(f"/mock/{mock_test.test_number}/listening/")

    # Sequence enforcement: if already completed reading, advance them
    if full_mock.current_step == "reading":
        return redirect(f"/mock/{mock_test.test_number}/reading/")
    elif full_mock.current_step == "reading_done":
        return redirect(f"/mock/{mock_test.test_number}/reading/complete/")
    elif full_mock.current_step == "writing":
        return redirect(f"/mock/{mock_test.test_number}/writing/")
    elif full_mock.current_step == "completed":
        return redirect(f"/mock/{mock_test.test_number}/consolidated-result/")

    listening_attempt = full_mock.listening_attempt
    return render(request, "exam/module_complete_interstitial.html", {
        "mock_test": mock_test,
        "full_mock": full_mock,
        "current_module_name": "Listening",
        "completed_attempt": listening_attempt,
        "stages": {
            "listening": "completed",  # Green
            "reading": "pending",      # Blue
            "writing": "gray",         # Blue/Pending
        },
        "next_module_post_url": f"/mock/{mock_test.test_number}/reading/",
    })


# --- STAGE 2: READING ---

@login_required
def full_mock_reading_view(request, mock_id):
    """
    GET or POST /mock/<id>/reading/
    Server-Side Rendered multi-passage reading interface with strict sequence enforcement.
    POST advances step from listening_done -> reading and redirects to GET.
    """
    if not is_candidate(request.user):
        messages.error(request, "Candidates only.")
        return redirect("bcl:dashboard")

    mock_test = get_mock_test_object(mock_id)
    if not mock_test:
        raise Http404(f"Mock test {mock_id} not found.")

    reading_mod = get_object_or_404(
        ExamModule, mock_test=mock_test, module_type=ExamModule.ModuleType.READING, is_active=True
    )

    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        now = timezone.now()

        full_mock = (
            FullMockAttempt.objects.select_for_update()
            .filter(candidate=request.user, mock_test=mock_test, status=FullMockAttempt.AttemptStatus.IN_PROGRESS)
            .order_by("-started_at")
            .first()
        )

        if not full_mock:
            # Standalone reading mode
            active_att = (
                CandidateAttempt.objects.select_for_update()
                .filter(candidate=request.user, module=reading_mod, status=CandidateAttempt.AttemptStatus.IN_PROGRESS)
                .order_by("-started_at")
                .first()
            )
            if active_att:
                attempt = expire_attempt_if_needed(active_att)
            if not active_att or attempt.status != CandidateAttempt.AttemptStatus.IN_PROGRESS:
                attempt = CandidateAttempt.objects.create(
                    candidate=request.user,
                    module=reading_mod,
                    full_mock=None,
                    started_at=now,
                    expires_at=now + timedelta(minutes=reading_mod.duration_minutes),
                    status=CandidateAttempt.AttemptStatus.IN_PROGRESS,
                )
            return redirect("bcl:exam_session", attempt_id=attempt.pk)

        # Sequence Guard: candidate must have finished Listening
        if full_mock.current_step == "listening":
            messages.warning(request, "You must complete and submit the Listening module first.")
            return redirect(f"/mock/{mock_test.test_number}/listening/")

        # If incoming from listening_done via Form POST, advance step to reading
        if request.method == "POST":
            if full_mock.current_step == "listening_done":
                full_mock.current_step = "reading"
                full_mock.save(update_fields=["current_step"])
            return redirect(f"/mock/{mock_test.test_number}/reading/")

        # Check if reading already finished
        if full_mock.current_step == "reading_done":
            return redirect(f"/mock/{mock_test.test_number}/reading/complete/")
        elif full_mock.current_step == "writing":
            return redirect(f"/mock/{mock_test.test_number}/writing/")
        elif full_mock.current_step == "completed":
            return redirect(f"/mock/{mock_test.test_number}/consolidated-result/")

        # Ensure reading CandidateAttempt exists
        if not full_mock.reading_attempt:
            reading_att = CandidateAttempt.objects.create(
                candidate=request.user,
                module=reading_mod,
                full_mock=full_mock,
                started_at=now,
                expires_at=now + timedelta(minutes=reading_mod.duration_minutes),
                status=CandidateAttempt.AttemptStatus.IN_PROGRESS,
            )
            full_mock.reading_attempt = reading_att
            full_mock.current_step = "reading"
            full_mock.save(update_fields=["reading_attempt", "current_step"])
        else:
            reading_att = expire_attempt_if_needed(full_mock.reading_attempt)
            if reading_att.status != CandidateAttempt.AttemptStatus.IN_PROGRESS:
                full_mock.current_step = "reading_done"
                full_mock.save(update_fields=["current_step"])
                return redirect(f"/mock/{mock_test.test_number}/reading/complete/")

    return redirect("bcl:exam_session", attempt_id=full_mock.reading_attempt.pk)


@login_required
@require_POST
def full_mock_reading_submit(request, mock_id):
    """
    POST /mock/<id>/reading/submit/ or POST /mock/<attempt_id>/reading/submit/
    Processes student responses for reading, grades 0-40, and 302 redirects to:
      - Full Mock: /mock/<id>/reading/complete/
      - Standalone: /result/<attempt_id>/
    """
    if not is_candidate(request.user):
        messages.error(request, "Candidates only.")
        return redirect("bcl:dashboard")

    attempt = None
    mock_test = get_mock_test_object(mock_id)
    if mock_test:
        reading_mod = ExamModule.objects.filter(mock_test=mock_test, module_type=ExamModule.ModuleType.READING).first()
        if reading_mod:
            attempt = (
                CandidateAttempt.objects.filter(candidate=request.user, module=reading_mod, status=CandidateAttempt.AttemptStatus.IN_PROGRESS)
                .order_by("-started_at")
                .first()
            )
    if not attempt:
        attempt = CandidateAttempt.objects.filter(pk=mock_id, candidate=request.user).first()

    if not attempt:
        completed = CandidateAttempt.objects.filter(candidate=request.user, module__module_type=ExamModule.ModuleType.READING).order_by("-started_at").first()
        if completed and completed.full_mock:
            return redirect(f"/mock/{completed.module.mock_test.test_number}/reading/complete/")
        elif completed:
            return redirect(f"/result/{completed.pk}/")
        return redirect("bcl:dashboard")

    test_number = attempt.module.mock_test.test_number

    # Execute submission via submit_exam core logic
    submit_exam(request, attempt.pk)

    if attempt.full_mock:
        full_mock = attempt.full_mock
        full_mock.current_step = "writing"
        full_mock.save(update_fields=["current_step"])
        return redirect(f"/mock/{test_number}/writing/")

    return redirect(f"/result/{attempt.pk}/")


@login_required
@require_GET
def full_mock_reading_complete(request, mock_id):
    """
    GET /mock/<id>/reading/complete/
    SSR Interstitial showing:
    - Listening: Green (Completed)
    - Reading: Green (Completed)
    - Writing: Blue (Pending)
    Actions:
    - "View Current Result" (GET)
    - "Go to Next Module" (Form POST to /mock/<id>/writing/)
    """
    if not is_candidate(request.user):
        messages.error(request, "Candidates only.")
        return redirect("bcl:dashboard")

    mock_test = get_mock_test_object(mock_id)
    if not mock_test:
        raise Http404(f"Mock test {mock_id} not found.")

    full_mock = (
        FullMockAttempt.objects.filter(candidate=request.user, mock_test=mock_test)
        .order_by("-started_at")
        .first()
    )
    if not full_mock:
        return redirect(f"/mock/{mock_test.test_number}/listening/")

    # Sequence check
    if full_mock.current_step == "writing":
        return redirect(f"/mock/{mock_test.test_number}/writing/")
    elif full_mock.current_step == "completed":
        return redirect(f"/mock/{mock_test.test_number}/consolidated-result/")

    reading_attempt = full_mock.reading_attempt
    return render(request, "exam/module_complete_interstitial.html", {
        "mock_test": mock_test,
        "full_mock": full_mock,
        "current_module_name": "Reading",
        "completed_attempt": reading_attempt,
        "stages": {
            "listening": "completed",  # Green
            "reading": "completed",    # Green
            "writing": "pending",      # Blue
        },
        "next_module_post_url": f"/mock/{mock_test.test_number}/writing/",
    })


# --- STAGE 3: WRITING ---

@login_required
def full_mock_writing_view(request, mock_id):
    """
    GET or POST /mock/<id>/writing/
    Backend-driven Writing interface for Task 1 & Task 2 textareas.
    POST advances step from reading_done -> writing and redirects to GET.
    """
    if not is_candidate(request.user):
        messages.error(request, "Candidates only.")
        return redirect("bcl:dashboard")

    mock_test = get_mock_test_object(mock_id)
    if not mock_test:
        raise Http404(f"Mock test {mock_id} not found.")

    writing_mod = get_object_or_404(
        ExamModule, mock_test=mock_test, module_type=ExamModule.ModuleType.WRITING, is_active=True
    )

    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        now = timezone.now()

        full_mock = (
            FullMockAttempt.objects.select_for_update()
            .filter(candidate=request.user, mock_test=mock_test, status=FullMockAttempt.AttemptStatus.IN_PROGRESS)
            .order_by("-started_at")
            .first()
        )

        if not full_mock:
            # Standalone writing practice
            active_att = (
                CandidateAttempt.objects.select_for_update()
                .filter(candidate=request.user, module=writing_mod, status=CandidateAttempt.AttemptStatus.IN_PROGRESS)
                .order_by("-started_at")
                .first()
            )
            if active_att:
                attempt = expire_attempt_if_needed(active_att)
            if not active_att or attempt.status != CandidateAttempt.AttemptStatus.IN_PROGRESS:
                attempt = CandidateAttempt.objects.create(
                    candidate=request.user,
                    module=writing_mod,
                    full_mock=None,
                    started_at=now,
                    expires_at=now + timedelta(minutes=writing_mod.duration_minutes),
                    status=CandidateAttempt.AttemptStatus.IN_PROGRESS,
                )
            return redirect("bcl:exam_session", attempt_id=attempt.pk)

        # Sequence Guard: Listening and Reading must be completed
        if full_mock.current_step in ("listening", "listening_done"):
            messages.warning(request, "You must complete Listening and Reading before Writing.")
            return redirect(f"/mock/{mock_test.test_number}/listening/")
        elif full_mock.current_step in ("reading", "reading_done"):
            if full_mock.reading_attempt and full_mock.reading_attempt.status != CandidateAttempt.AttemptStatus.IN_PROGRESS:
                full_mock.current_step = "writing"
                full_mock.save(update_fields=["current_step"])
            elif full_mock.current_step == "reading":
                messages.warning(request, "You must complete the Reading module before Writing.")
                return redirect(f"/mock/{mock_test.test_number}/reading/")
            else:
                full_mock.current_step = "writing"
                full_mock.save(update_fields=["current_step"])

        if full_mock.current_step == "completed":
            return redirect(f"/mock/{mock_test.test_number}/consolidated-result/")

        # Ensure writing CandidateAttempt exists
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
            full_mock.current_step = "writing"
            full_mock.save(update_fields=["writing_attempt", "current_step"])
        else:
            writing_att = expire_attempt_if_needed(full_mock.writing_attempt)
            if writing_att.status != CandidateAttempt.AttemptStatus.IN_PROGRESS:
                full_mock.current_step = "completed"
                full_mock.save(update_fields=["current_step"])
                return redirect(f"/mock/{mock_test.test_number}/consolidated-result/")

    return redirect("bcl:exam_session", attempt_id=full_mock.writing_attempt.pk)


@login_required
@require_POST
def full_mock_writing_submit(request, mock_id):
    """
    POST /mock/<id>/writing/submit/ or POST /mock/<attempt_id>/writing/submit/
    Submits Task 1 & Task 2 textareas. Marks status as "Under Review".
    Redirects directly to:
      - Full Mock: /mock/<id>/consolidated-result/
      - Standalone: /result/<attempt_id>/
    """
    if not is_candidate(request.user):
        messages.error(request, "Candidates only.")
        return redirect("bcl:dashboard")

    attempt = None
    mock_test = get_mock_test_object(mock_id)
    if mock_test:
        writing_mod = ExamModule.objects.filter(mock_test=mock_test, module_type=ExamModule.ModuleType.WRITING).first()
        if writing_mod:
            attempt = (
                CandidateAttempt.objects.filter(candidate=request.user, module=writing_mod, status=CandidateAttempt.AttemptStatus.IN_PROGRESS)
                .order_by("-started_at")
                .first()
            )
    if not attempt:
        attempt = CandidateAttempt.objects.filter(pk=mock_id, candidate=request.user).first()

    if not attempt:
        completed = CandidateAttempt.objects.filter(candidate=request.user, module__module_type=ExamModule.ModuleType.WRITING).order_by("-started_at").first()
        if completed and completed.full_mock:
            return redirect(f"/mock/{completed.module.mock_test.test_number}/consolidated-result/")
        elif completed:
            return redirect(f"/result/{completed.pk}/")
        return redirect("bcl:dashboard")

    test_number = attempt.module.mock_test.test_number

    with transaction.atomic():
        now = timezone.now()
        attempt.status = CandidateAttempt.AttemptStatus.SUBMITTED
        attempt.submitted_at = now
        attempt.save(update_fields=["status", "submitted_at"])

        if attempt.full_mock:
            full_mock = attempt.full_mock
            full_mock.status = FullMockAttempt.OverallStatus.SUBMITTED
            full_mock.current_step = "completed"
            full_mock.submitted_at = now
            full_mock.calculate_overall_score()
            full_mock.save(update_fields=["status", "current_step", "submitted_at", "overall_band_score"])
            return redirect(f"/mock/{test_number}/consolidated-result/")

    return redirect(f"/result/{attempt.pk}/")


# --- CONSOLIDATED RESULT ---

@login_required
@require_GET
def full_mock_consolidated_result(request, mock_id):
    """
    GET /mock/<id>/consolidated-result/
    Final Consolidated Report Page displaying overall status:
    Writing: Under Review, Overall: Pending validation of all reviews.
    """
    if not is_candidate(request.user):
        messages.error(request, "Candidates only.")
        return redirect("bcl:dashboard")

    mock_test = get_mock_test_object(mock_id)
    if not mock_test:
        raise Http404(f"Mock test {mock_id} not found.")

    full_mock = (
        FullMockAttempt.objects.filter(candidate=request.user, mock_test=mock_test)
        .order_by("-started_at")
        .first()
    )
    if not full_mock:
        messages.info(request, "No full mock attempt found for this test.")
        return redirect("bcl:dashboard")

    return render(request, "exam/consolidated_result.html", {
        "mock_test": mock_test,
        "full_mock": full_mock,
        "listening_attempt": full_mock.listening_attempt,
        "reading_attempt": full_mock.reading_attempt,
        "writing_attempt": full_mock.writing_attempt,
    })


# ==============================================================================
# MODE A: INDEPENDENT MODULE RESULT ROUTE
# ==============================================================================

@login_required
@require_GET
def standalone_result_redirect(request, attempt_id):
    """
    GET /result/<attempt_id>/
    Direct clean URL redirecting to candidate's question-review page.
    """
    return redirect("bcl:exam_result", attempt_id=attempt_id)

