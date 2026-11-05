import os
from datetime import timedelta
import json
import logging
import uuid
import mimetypes

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import (
    CandidateAnswer, CandidateAttempt, ExamModule, Question, FullMockAttempt,
    IELTSMockTest, get_writing_task_questions,
)
from .scoring import finalize_attempt_score


MAX_ANSWER_LENGTH = 20000
logger = logging.getLogger(__name__)


def is_audio_file(field):
    """Return whether a stored file has a browser-playable audio extension."""
    return bool(
        field
        and field.name
        and os.path.splitext(field.name)[1].lower().lstrip(".")
        in {"mp3", "wav", "ogg", "m4a", "aac", "webm"}
    )


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

            if locked.full_mock_id:
                fm = FullMockAttempt.objects.select_for_update().filter(pk=locked.full_mock_id).first()
                if fm and fm.status == FullMockAttempt.AttemptStatus.IN_PROGRESS:
                    if fm.current_step == "listening" and (fm.listening_attempt_id == locked.pk or not fm.listening_attempt_id):
                        fm.current_step = "reading"
                        fm.save(update_fields=["current_step"])
                    elif fm.current_step == "reading" and (fm.reading_attempt_id == locked.pk or not fm.reading_attempt_id):
                        fm.current_step = "writing"
                        fm.save(update_fields=["current_step"])
                    elif fm.current_step == "writing" and (fm.writing_attempt_id == locked.pk or not fm.writing_attempt_id):
                        fm.status = CandidateAttempt.AttemptStatus.AUTO_SUBMITTED
                        fm.current_step = "completed"
                        fm.submitted_at = now
                        fm.calculate_overall_score()
                        fm.save()
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

    if module.module_type == ExamModule.ModuleType.LISTENING:
        url = reverse("bcl:mock_listening", args=[module.mock_test_id])
        return redirect(f"{url}?mode=individual")
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


def annotate_question_groups(questions, start_counter=1):
    """
    Groups consecutive questions in a section by question_type and question_instructions.
    Calculates global question numbers and attaches group_header to the first question of each group.
    """
    import re
    q_list = list(questions)
    groups = []
    current_group = None
    global_counter = start_counter

    for q in q_list:
        b_count = 1
        if q.question_type == Question.QuestionType.FILL_BLANK:
            p_c = len(re.findall(r"_{3,}", q.question_text))
            a_c = len([x for x in (q.correct_answer or "").split(";;;") if x.strip()])
            b_count = max(p_c, a_c, q.answer_count or 1, 1)
        elif q.question_type == Question.QuestionType.MULTI_SELECT and (q.answer_count or 1) > 1:
            b_count = q.answer_count

        inst = (q.question_instructions or "").strip()
        is_new = (
            current_group is None
            or q.question_type != current_group["type"]
            or (bool(inst) and bool(current_group["instruction"]) and inst != current_group["instruction"])
        )

        q.global_num = global_counter
        q.blank_count = b_count

        if is_new:
            type_display = q.get_question_type_display().upper()
            if q.question_type == "tfng":
                type_display = "TRUE / FALSE / NOT GIVEN"
            elif q.question_type == "ynng":
                type_display = "YES / NO / NOT GIVEN"
            elif q.question_type == "mcq":
                type_display = "MULTIPLE CHOICE"
            elif q.question_type == "fill_blank":
                type_display = "FILL IN THE BLANK"

            current_group = {
                "type": q.question_type,
                "type_display": type_display,
                "instruction": inst,
                "start_num": global_counter,
                "end_num": global_counter + b_count - 1,
                "first_question": q,
            }
            groups.append(current_group)
        else:
            if inst and not current_group["instruction"]:
                current_group["instruction"] = inst
            current_group["end_num"] = global_counter + b_count - 1

        global_counter += b_count

    for g in groups:
        r = f"Q{g['start_num']}" if g["start_num"] == g["end_num"] else f"Q{g['start_num']}–Q{g['end_num']}"
        header = {
            "type_display": g["type_display"],
            "range_label": r,
            "instruction": g["instruction"],
        }
        # For matching/matching_information groups, attach the options from
        # the first question so the template can render them once at the
        # group header level rather than repeating for every question.
        if g["type"] in (
            Question.QuestionType.MATCHING,
            Question.QuestionType.MATCHING_INFORMATION,
        ):
            header["matching_options"] = list(
                g["first_question"].options.order_by("order", "option_key")
            )
        g["first_question"].group_header = header

    return q_list, global_counter



# The legacy bridge auto-submitted whenever checkAnswers() was called.
# The authoritative Listening bridge is generated by render_listening_html().
# Keep a single explicit submission owner to prevent cross-module side effects.
LISTENING_BRIDGE_TEMPLATE = ""



def get_mock_test_object(mock_id):
    """Resolve IELTSMockTest by pk or test_number."""
    return (
        IELTSMockTest.objects.filter(pk=mock_id, is_published=True).first()
        or IELTSMockTest.objects.filter(test_number=mock_id, is_published=True).first()
    )


def get_listening_filepath(mock_num, module=None):
    """Resolve an uploaded listening HTML asset, then the legacy disk asset."""
    uploaded_file = (
        getattr(module, "module_file", None)
        or getattr(module, "listening_html_file", None)
    )
    if uploaded_file:
        try:
            uploaded_path = uploaded_file.path
        except (AttributeError, NotImplementedError, ValueError):
            uploaded_path = None
        if uploaded_path and os.path.isfile(uploaded_path):
            return uploaded_path

    candidates = [
        os.path.join(r"D:\BCL-Bhuiyan\listening", f"listening-mock-{mock_num}.html"),
        os.path.join(r"D:\BCL-Bhuiyan\bcl_bhuiyan\listening", f"listening-mock-{mock_num}.html"),
        os.path.join(settings.BASE_DIR, "listening", f"listening-mock-{mock_num}.html"),
        os.path.join(settings.BASE_DIR.parent, "listening", f"listening-mock-{mock_num}.html"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def parse_listening_answer_key(mock_num, module=None):
    """
    Parse the official answer key for a listening mock test directly from its HTML file.
    Supports single keys, lists of synonyms, range keys (e.g. q11-12, q13_14), and pickGroups.
    Returns a dict mapping string question number ('1'..'40') to formatted string or list of valid answers.
    """
    import re
    import ast

    filepath = get_listening_filepath(mock_num, module)
    if not filepath or not os.path.exists(filepath):
        return {}

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()
    except Exception as exc:
        logger.error("Error reading listening file %s for answer key: %s", filepath, exc)
        return {}

    answers = {}
    m = re.search(r'(?:const|let|var)\s+correctAnswers\s*=\s*(\{[\s\S]*?\n\s*\};?)', txt)
    if not m:
        m = re.search(r'(?:const|let|var)\s+correctAnswers\s*=\s*(\{[\s\S]*?\});', txt)

    if m:
        raw_block = m.group(1).rstrip(';').strip()
        matches = re.findall(r'[\'"]?([a-zA-Z0-9_\-]+)[\'"]?\s*:\s*(\[[^\]]*\]|[\'"][^\'"]*[\'"]|[^,\n}]+)', raw_block)
        for k_raw, v_raw in matches:
            k = k_raw.replace('q', '').strip()
            v_str = v_raw.strip().rstrip(',')
            if v_str.startswith('[') and v_str.endswith(']'):
                try:
                    val = ast.literal_eval(v_str)
                except Exception:
                    val = re.findall(r'[\'"]([^\'"]*)[\'"]', v_str)
            elif (v_str.startswith('"') and v_str.endswith('"')) or (v_str.startswith("'") and v_str.endswith("'")):
                val = v_str[1:-1]
            else:
                val = v_str.strip("'\"")

            sep = '-' if '-' in k else ('_' if '_' in k else None)
            if sep:
                parts = k.split(sep)
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    p_start, p_end = int(parts[0]), int(parts[1])
                    val_str = ", ".join(val) if isinstance(val, (list, tuple)) else str(val)
                    for num in range(p_start, p_end + 1):
                        answers[str(num)] = val_str
                else:
                    answers[k] = val
            else:
                answers[k] = val

    pg_match = re.search(r'(?:const|let|var)\s+pickGroups\s*=\s*(\[[\s\S]*?\]);', txt)
    if pg_match:
        for obj_str in re.findall(r'\{[^{}]*\}', pg_match.group(1)):
            start_m = re.search(r'qStart\s*:\s*(\d+)', obj_str)
            end_m = re.search(r'qEnd\s*:\s*(\d+)', obj_str)
            target_m = re.search(r'target\s*:\s*(\[[^\]]*\])', obj_str)
            if start_m and end_m and target_m:
                q_start = int(start_m.group(1))
                q_end = int(end_m.group(1))
                try:
                    targets = ast.literal_eval(target_m.group(1))
                except Exception:
                    targets = re.findall(r'[\'"]([^\'"]*)[\'"]', target_m.group(1))
                targets_str = ", ".join(targets)
                for q_num in range(q_start, q_end + 1):
                    if str(q_num) not in answers:
                        answers[str(q_num)] = targets_str

    return answers


def get_listening_review_data(attempt):
    """
    Synthesize complete 40-question review data for a listening CandidateAttempt,
    matching the exact completion modal interface displayed upon listening submission.
    """
    if not attempt or not getattr(attempt, "module", None):
        return None

    module = attempt.module
    mock_test = module.mock_test
    mock_num = mock_test.test_number if mock_test else 1
    server_keys = parse_listening_answer_key(mock_num, module)
    payload = attempt.answers_payload or {}
    cand_answers = payload.get("answers", {}) if isinstance(payload, dict) else {}
    db_answers = {
        a.question.order: a
        for a in CandidateAnswer.objects.filter(attempt=attempt).select_related("question")
    }

    questions = []
    correct_count = 0

    for q_num in range(1, 41):
        k = str(q_num)
        ans_item = cand_answers.get(k) or cand_answers.get(f"q{q_num}")
        user_answer = ""
        correct_answer = ""
        is_correct = False

        if isinstance(ans_item, dict):
            user_answer = str(ans_item.get("user_answer", "")).strip()
            if user_answer.lower() in ("no answer", "none", "null"):
                user_answer = ""
            is_correct = bool(ans_item.get("is_correct", False))
            correct_answer = str(ans_item.get("correct_answer", "")).strip()
        elif isinstance(ans_item, str):
            user_answer = ans_item.strip()
            if user_answer.lower() in ("no answer", "none", "null"):
                user_answer = ""

        if not user_answer and q_num in db_answers:
            db_ans = db_answers[q_num]
            user_answer = (db_ans.answer_text or "").strip()
            if user_answer.lower() in ("no answer", "none", "null"):
                user_answer = ""
            is_correct = bool(db_ans.is_correct)

        if not correct_answer:
            raw_key = server_keys.get(k) or server_keys.get(f"q{q_num}")
            if isinstance(raw_key, (list, tuple)):
                correct_answer = " / ".join(str(x) for x in raw_key)
            elif raw_key:
                correct_answer = str(raw_key)
            else:
                correct_answer = "-"

        if not is_correct and user_answer and correct_answer and correct_answer != "-":
            raw_key = server_keys.get(k) or server_keys.get(f"q{q_num}")
            if isinstance(raw_key, (list, tuple)):
                valid_lower = [str(x).strip().lower() for x in raw_key]
                if user_answer.lower() in valid_lower:
                    is_correct = True
            elif isinstance(raw_key, str) and raw_key:
                tokens = [t.strip().lower() for t in raw_key.replace('/', ',').split(',') if t.strip()]
                if user_answer.lower() in tokens or user_answer.lower() == raw_key.strip().lower():
                    is_correct = True

        if is_correct:
            correct_count += 1

        part_num = ((q_num - 1) // 10) + 1
        questions.append({
            "num": q_num,
            "part": part_num,
            "user_answer": user_answer,
            "has_answer": bool(user_answer),
            "correct_answer": correct_answer,
            "is_correct": is_correct,
            "status_label": "Correct" if is_correct else "Incorrect",
            "status_class": "correct" if is_correct else "incorrect",
        })

    raw_score = attempt.raw_score if attempt.raw_score is not None else correct_count
    from .scoring import band_for_raw
    from decimal import Decimal
    band_score = str(attempt.band_score) if attempt.band_score is not None else str(band_for_raw(ExamModule.ModuleType.LISTENING, raw_score))

    time_taken_str = "00:00"
    if attempt.submitted_at and attempt.started_at:
        seconds = max(0, int((attempt.submitted_at - attempt.started_at).total_seconds()))
        time_taken_str = f"{seconds // 60:02d}:{seconds % 60:02d}"

    audio_url = f"/static/listening_audio/mock_{mock_num}_full.mp3"
    audio_path = os.path.join(settings.BASE_DIR, "static", "listening_audio", f"mock_{mock_num}_full.mp3")
    if not os.path.exists(audio_path):
        audio_url = ""

    candidate = attempt.candidate
    cand_full_name = f"{candidate.first_name} {candidate.last_name}".strip() if candidate and hasattr(candidate, 'first_name') else ""
    candidate_name = cand_full_name if cand_full_name else (candidate.username if candidate and hasattr(candidate, 'username') else "Candidate")
    candidate_username = candidate.username if candidate and hasattr(candidate, 'username') else "candidate"

    return {
        "attempt": attempt,
        "candidate": candidate,
        "candidate_name": candidate_name,
        "candidate_username": candidate_username,
        "mock_test": mock_test,
        "mock_num": mock_num,
        "raw_score": raw_score,
        "band_score": band_score,
        "correct_count": correct_count,
        "wrong_count": 40 - correct_count,
        "time_taken": time_taken_str,
        "questions": questions,
        "audio_url": audio_url,
    }


def render_listening_html(request, attempt):
    r"""
    Render client-side raw HTML listening module from D:\BCL-Bhuiyan\listening\
    Styled to seamlessly match the website design system (Geist font, modern cards, indigo accents),
    with full student info, score, and answer payload persisted to database on submit, plus modern completion modal.
    Authoritative 35-minute timer ensures 35:00 countdown both in dashboard and exam session.
    Audio engine enforces continuous IELTS audio: all sections play seamlessly together from start to finish.
    Includes initial exam instruction modal upon entry and full exam integrity tab-switching monitoring with auto-submit.
    """
    import os
    import json
    from django.middleware.csrf import get_token
    from .scoring import band_for_raw

    mock_test = attempt.module.mock_test
    mock_num = mock_test.test_number
    filepath = get_listening_filepath(mock_num, attempt.module)
    if not filepath or not os.path.exists(filepath):
        logger.error("Could not find listening file for Mock %s", mock_num)
        return HttpResponse(f"Error: listening-mock-{mock_num}.html not found.", status=404)

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            html_content = f.read()
    except Exception as exc:
        logger.error("Error reading listening file %s: %s", filepath, exc)
        return HttpResponse(f"Error loading listening module for Mock Test {mock_num}.", status=500)

    # Enforce authoritative 40-minute module duration
    now = timezone.now()
    if attempt.module.duration_minutes != 40:
        attempt.module.duration_minutes = 40
        attempt.module.save(update_fields=["duration_minutes"])

    max_seconds = 40 * 60  # 2400 seconds
    server_answer_key = parse_listening_answer_key(mock_num, attempt.module)
    server_answer_key_json = json.dumps(server_answer_key)
    if not attempt.expires_at:
        attempt.expires_at = now + timedelta(seconds=max_seconds)
        attempt.save(update_fields=["expires_at"])
        remaining_seconds = max_seconds
    else:
        remaining_seconds = int((attempt.expires_at - now).total_seconds())
        if remaining_seconds > max_seconds:
            attempt.expires_at = now + timedelta(seconds=max_seconds)
            attempt.save(update_fields=["expires_at"])
            remaining_seconds = max_seconds
        elif remaining_seconds <= 0:
            remaining_seconds = max_seconds
            attempt.expires_at = now + timedelta(seconds=max_seconds)
            attempt.save(update_fields=["expires_at"])

    csrf_token = get_token(request)
    mock_id = mock_test.pk
    is_full_mock = bool(attempt.full_mock_id)
    submit_url = reverse("bcl:mock_listening_submit", args=[mock_id])
    next_url = reverse("bcl:mock_reading", args=[mock_id]) if is_full_mock else reverse("bcl:dashboard")
    violation_url = reverse("bcl:report_exam_violation", args=[attempt.pk])
    ended_url = reverse("bcl:full_mock_ended", args=[attempt.full_mock_id]) if is_full_mock else reverse("bcl:exam_ended", args=[attempt.pk])
    candidate_name = request.user.get_full_name() or request.user.username
    candidate_username = request.user.username

    # Resolve Unified Continuous Merged Audio File if available
    merged_audio_rel = f"/static/listening_audio/mock_{mock_num}_full.mp3"
    merged_audio_path = os.path.join(settings.BASE_DIR, "static", "listening_audio", f"mock_{mock_num}_full.mp3")
    merged_audio_url = merged_audio_rel if os.path.exists(merged_audio_path) else ""

    # Injected Website Design System Integration (Geist & Geist Mono fonts, matching exam.css)
    bcl_design_css = """
    <!-- BCL IELTS Website Design System Integration -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700;800&family=Geist+Mono:wght@500;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --font-sans: 'Geist', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            --font-mono: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            --bcl-primary: #4f46e5;
            --bcl-primary-dark: #4338ca;
            --bcl-primary-light: #eef2ff;
            --bcl-border-indigo: #c7d2fe;
            --bcl-text-main: #1e293b;
            --bcl-text-muted: #64748b;
            --bcl-border: #e2e8f0;
            --bcl-bg: #f8fafc;
        }

        *, *::before, *::after {
            box-sizing: border-box;
        }

        html, body {
            font-family: var(--font-sans) !important;
            padding-top: 60px !important;
            background-color: var(--bcl-bg) !important;
            color: var(--bcl-text-main) !important;
            -webkit-font-smoothing: antialiased;
        }

        body, button, input, select, textarea, div, p, span, table, th, td, label, h1, h2, h3, h4 {
            font-family: var(--font-sans) !important;
        }

        /* Suppress third-party links, disparate unstyled headers and raw/legacy modals completely across all mock files */
        .header:not(#bcl-exam-header),
        header:not(#bcl-exam-header),
        .fixed-header:not(#bcl-exam-header),
        .app-header:not(#bcl-exam-header),
        .telegram-link,
        .telegram-pin,
        #resultsModal,
        #result-modal,
        #results-modal,
        div[id*="result-modal"],
        div[id*="results-modal"],
        div[id*="resultsModal"],
        .modal-overlay:not(#bcl-listening-modal):not(#bcl-instruction-modal):not(#bcl-violation-modal),
        .modal:not(#bcl-listening-modal):not(#bcl-instruction-modal):not(#bcl-violation-modal) {
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
            pointer-events: none !important;
            z-index: -99999 !important;
            position: absolute !important;
            left: -99999px !important;
            top: -99999px !important;
            width: 0 !important;
            height: 0 !important;
            max-width: 0 !important;
            max-height: 0 !important;
            overflow: hidden !important;
        }

        /* Unified Website Exam Header */
        #bcl-exam-header {
            position: fixed !important;
            top: 0 !important;
            left: 0 !important;
            right: 0 !important;
            height: 60px !important;
            background: linear-gradient(to bottom, #eff6ff, #eef2ff, rgba(250, 245, 255, 0.98)) !important;
            backdrop-filter: blur(16px) !important;
            -webkit-backdrop-filter: blur(16px) !important;
            border-bottom: 1px solid #c7d2fe !important;
            display: flex !important;
            align-items: center !important;
            justify-content: space-between !important;
            padding: 0 20px !important;
            z-index: 10000 !important;
            box-shadow: 0 1px 3px 0 rgba(79, 70, 229, 0.08) !important;
            box-sizing: border-box !important;
        }

        .bcl-header-group {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .bcl-back-link {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 14px;
            background: #ffffff;
            border: 1px solid #c7d2fe;
            border-radius: 8px;
            color: #4f46e5;
            font-size: 13px;
            font-weight: 600;
            text-decoration: none;
            transition: all 0.15s ease;
        }
        .bcl-back-link:hover {
            background: #eef2ff;
            border-color: #818cf8;
            color: #3730a3;
        }

        .bcl-brand-badge {
            width: 32px;
            height: 32px;
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
            font-size: 15px;
            box-shadow: 0 2px 6px rgba(79, 70, 229, 0.28);
        }

        .bcl-title-box {
            display: flex;
            flex-direction: column;
        }

        .bcl-main-title {
            font-size: 13.5px;
            font-weight: 700;
            color: #0f172a;
            line-height: 1.2;
        }

        .bcl-sub-meta {
            font-size: 11px;
            color: #64748b;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .bcl-stage-pill {
            background: #eef2ff;
            color: #4338ca;
            border: 1px solid #c7d2fe;
            padding: 2px 8px;
            border-radius: 9999px;
            font-size: 10.5px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }

        .bcl-timer-pill {
            background: #ffffff;
            border: 1px solid #c7d2fe;
            border-radius: 9999px;
            padding: 6px 16px;
            display: flex;
            align-items: center;
            gap: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.03);
        }

        #bclHeaderTimer {
            font-family: var(--font-mono) !important;
            font-size: 14px;
            font-weight: 700;
            letter-spacing: 0.05em;
            font-variant-numeric: tabular-nums;
            color: #1e293b;
            min-width: 48px;
        }

        #bclHeaderTimer.warning {
            color: #dc2626 !important;
            animation: bclTimerPulse 1s infinite alternate;
        }

        @keyframes bclTimerPulse {
            from { opacity: 1; }
            to { opacity: 0.45; }
        }

        .bcl-user-badge {
            font-size: 12.5px;
            color: #475569;
            background: #f1f5f9;
            padding: 6px 12px;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
        }

        .bcl-info-btn {
            background: #ffffff;
            border: 1px solid #c7d2fe;
            border-radius: 8px;
            color: #4f46e5;
            font-size: 12px;
            font-weight: 600;
            padding: 6px 12px;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 5px;
            transition: all 0.15s ease;
        }
        .bcl-info-btn:hover {
            background: #eef2ff;
            border-color: #818cf8;
        }

        .bcl-submit-btn {
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
            color: #ffffff;
            border: none;
            border-radius: 8px;
            padding: 8px 18px;
            font-size: 13.5px;
            font-weight: 700;
            cursor: pointer;
            box-shadow: 0 3px 10px rgba(79, 70, 229, 0.3);
            transition: all 0.15s ease;
        }
        .bcl-submit-btn:hover {
            background: linear-gradient(135deg, #4338ca 0%, #6d28d9 100%);
            transform: translateY(-1px);
        }

        /* =========================================================================
           Unified Fixed Audio Bar across all 30 Mock Tests (Clean, centered, no overlap)
           ========================================================================= */
        .audio-bar,
        .listening-player-bar,
        .audio-player-container,
        div[class*="audio-player"] {
            position: fixed !important;
            top: 60px !important;
            left: 0 !important;
            right: 0 !important;
            transform: none !important;
            width: 100% !important;
            max-width: 100% !important;
            height: 58px !important;
            z-index: 9999 !important;
            background: linear-gradient(to right, #f8fafc, #eff6ff, #f8fafc) !important;
            border-bottom: 1px solid #c7d2fe !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            padding: 0 20px !important;
            box-shadow: 0 2px 6px rgba(79, 70, 229, 0.06) !important;
            box-sizing: border-box !important;
            gap: 16px !important;
        }

        /* Push main question content down below 60px header + 58px audio bar so questions NEVER overlap! */
        .main-container,
        .main-area,
        #questionsPanel,
        .questions-panel,
        .left-panel,
        .right-panel {
            padding-top: 135px !important;
            margin-top: 0 !important;
        }

        /* Suppress premature Check Answers / Deliver buttons on the exam page */
        #deliver-button,
        #checkButton,
        #check-btn,
        #btnCheckAnswers,
        .footer__deliverButton___3FM07,
        .deliver-btn,
        .check-btn:not(#bclHeaderSubmitBtn),
        button[onclick*="checkAnswers"]:not(#bclHeaderSubmitBtn) {
            display: none !important;
        }

        /* Unify Master Play Button */
        .player-btn,
        .audio-play,
        .audio-btn-play,
        #play-pause-btn,
        #btnAudioPlay,
        #btnPlayPause {
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%) !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 9999px !important;
            padding: 8px 22px !important;
            font-size: 13.5px !important;
            font-weight: 700 !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 8px !important;
            cursor: pointer !important;
            box-shadow: 0 2px 8px rgba(79, 70, 229, 0.3) !important;
            transition: all 0.15s ease !important;
            min-width: 150px !important;
            height: 38px !important;
        }

        .player-btn.playing,
        .audio-play.playing,
        .audio-btn-play.playing,
        #play-pause-btn.playing,
        #btnAudioPlay.playing,
        #btnPlayPause.playing {
            background: linear-gradient(135deg, #059669 0%, #10b981 100%) !important;
            box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3) !important;
            cursor: default !important;
        }

        .audio-wave-bars {
            display: inline-flex;
            align-items: flex-end;
            gap: 2px;
            height: 13px;
        }
        .audio-wave-bars span {
            display: inline-block;
            width: 2.5px;
            background: #ffffff;
            border-radius: 9999px;
            height: 3px;
        }
        .audio-wave-bars.playing span:nth-child(1) { animation: audioWave 1.05s ease-in-out infinite alternate; }
        .audio-wave-bars.playing span:nth-child(2) { animation: audioWave 0.75s ease-in-out 0.15s infinite alternate; }
        .audio-wave-bars.playing span:nth-child(3) { animation: audioWave 1.25s ease-in-out 0.3s infinite alternate; }
        .audio-wave-bars.playing span:nth-child(4) { animation: audioWave 0.9s ease-in-out 0.1s infinite alternate; }
        @keyframes audioWave {
            0% { height: 3px; }
            50% { height: 13px; }
            100% { height: 4px; }
        }

        /* Hide skip buttons & lock scrubbing */
        #back10, #forward10, .skip-btn, .audio-btn-circle, #btnAudioBack, #btnAudioFwd {
            display: none !important;
        }

        #seekSlider, #progress-bar, .progress-container, #audioProgressContainer {
            pointer-events: none !important;
            opacity: 0.85 !important;
        }

        /* Cards & Section Panels */
        .question-card, .notes-card, .section-content, .ldm-task, .question-block, .question, .section-panel, .question-group {
            background: #ffffff !important;
            border: 1px solid #e2e8f0 !important;
            border-radius: 12px !important;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
            padding: 18px 22px !important;
            margin-bottom: 16px !important;
        }

        .section-banner {
            background: #eff6ff !important;
            border: 1px solid #c7d2fe !important;
            border-left: 4px solid #4f46e5 !important;
            border-radius: 8px !important;
            padding: 12px 18px !important;
            margin: 10px auto 16px auto !important;
            max-width: 1220px !important;
        }

        /* Input Controls */
        .answer-input, input[type="text"] {
            font-family: var(--font-sans) !important;
            font-size: 14px !important;
            font-weight: 500 !important;
            padding: 6px 12px !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 6px !important;
            background: #ffffff !important;
            color: #1e293b !important;
            transition: all 0.15s ease !important;
            box-shadow: inset 0 1px 2px rgba(0,0,0,0.03) !important;
        }
        .answer-input:focus, input[type="text"]:focus {
            outline: none !important;
            border-color: #6366f1 !important;
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2) !important;
        }

        /* Bottom Navigation Bar */
        .fixed-bottom, .nav-row, .bottom-nav, .footer-nav {
            position: fixed !important;
            bottom: 0 !important;
            left: 0 !important;
            right: 0 !important;
            height: 70px !important;
            background: rgba(255, 255, 255, 0.98) !important;
            backdrop-filter: blur(12px) !important;
            -webkit-backdrop-filter: blur(12px) !important;
            border-top: 1px solid #e2e8f0 !important;
            box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.04) !important;
            display: flex !important;
            align-items: center !important;
            justify-content: space-between !important;
            padding: 0 20px !important;
            z-index: 9999 !important;
        }

        /* Modern BCL Results Popup Modal */
        #bcl-listening-modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(15, 23, 42, 0.72);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            z-index: 999999;
            align-items: center;
            justify-content: center;
            padding: 16px;
            box-sizing: border-box;
            font-family: var(--font-sans) !important;
        }

        .bcl-modal-container {
            background: #ffffff;
            border-radius: 20px;
            max-width: 760px;
            width: 100%;
            max-height: 88vh;
            display: flex;
            flex-direction: column;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.28);
            border: 1px solid #e2e8f0;
            overflow: hidden;
            animation: bclFadeIn 0.22s ease-out;
        }

        @keyframes bclFadeIn {
            from { opacity: 0; transform: scale(0.96) translateY(6px); }
            to { opacity: 1; transform: scale(1) translateY(0); }
        }

        .bcl-modal-top {
            padding: 18px 24px;
            border-bottom: 1px solid #e2e8f0;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #ffffff;
        }

        .bcl-modal-score-banner {
            margin: 16px 24px 0 24px;
            padding: 16px 20px;
            background: linear-gradient(135deg, #eff6ff 0%, #e0e7ff 100%);
            border: 1px solid #c7d2fe;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: space-around;
            text-align: center;
        }

        .bcl-metric-title {
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            color: #4338ca;
            letter-spacing: 0.05em;
            margin-bottom: 2px;
        }

        .bcl-metric-value {
            font-size: 22px;
            font-weight: 800;
            color: #1e1b4b;
            font-family: var(--font-mono) !important;
        }

        .bcl-metric-divider {
            width: 1px;
            height: 34px;
            background: #c7d2fe;
        }

        .bcl-modal-table-scroll {
            flex: 1;
            overflow-y: auto;
            padding: 16px 24px;
        }

        .bcl-review-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13.5px;
        }

        .bcl-review-table th {
            background: #f8fafc;
            color: #475569;
            font-weight: 700;
            text-align: left;
            padding: 10px 14px;
            border-bottom: 2px solid #e2e8f0;
            position: sticky;
            top: 0;
            z-index: 10;
        }

        .bcl-review-table td {
            padding: 9px 14px;
            border-bottom: 1px solid #f1f5f9;
            color: #1e293b;
        }

        .bcl-status-pill {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
        }

        .bcl-status-pill.correct {
            background: #ecfdf5;
            color: #047857;
            border: 1px solid #a7f3d0;
        }

        .bcl-status-pill.incorrect {
            background: #fef2f2;
            color: #b91c1c;
            border: 1px solid #fecaca;
        }

        .bcl-modal-bottom {
            padding: 14px 24px;
            background: #f8fafc;
            border-top: 1px solid #e2e8f0;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
        }

        /* Initial Entry Examination Instruction Modal */
        #bcl-instruction-modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(15, 23, 42, 0.78);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            z-index: 999998;
            align-items: center;
            justify-content: center;
            padding: 16px;
            box-sizing: border-box;
            font-family: var(--font-sans) !important;
        }

        .bcl-instruction-dialog {
            background: #ffffff;
            border-radius: 20px;
            max-width: 680px;
            width: 100%;
            max-height: 90vh;
            display: flex;
            flex-direction: column;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.28);
            border: 1px solid #e2e8f0;
            overflow: hidden;
            animation: bclFadeIn 0.22s ease-out;
        }

        .bcl-instruction-header {
            padding: 20px 26px;
            border-bottom: 1px solid #e2e8f0;
            display: flex;
            align-items: center;
            gap: 16px;
            background: linear-gradient(to right, #eff6ff, #f8fafc);
        }

        .bcl-instruction-icon-badge {
            width: 44px;
            height: 44px;
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
            font-size: 20px;
            box-shadow: 0 3px 8px rgba(79, 70, 229, 0.3);
            flex-shrink: 0;
        }

        .bcl-instruction-title {
            margin: 4px 0 0 0;
            font-size: 18px;
            font-weight: 800;
            color: #0f172a;
            line-height: 1.25;
        }

        .bcl-instruction-sub {
            margin: 3px 0 0 0;
            font-size: 12px;
            color: #64748b;
        }

        .bcl-instruction-body {
            padding: 20px 26px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 14px;
        }

        .bcl-notice-card {
            display: flex;
            align-items: flex-start;
            gap: 14px;
            padding: 14px 16px;
            border-radius: 12px;
            font-size: 13px;
            line-height: 1.55;
        }

        .bcl-notice-card.audio-notice {
            background: #eff6ff;
            border: 1px solid #bfdbfe;
            color: #1e3a8a;
        }
        .bcl-notice-card.audio-notice strong {
            color: #1d4ed8;
            display: block;
            margin-bottom: 3px;
            font-size: 13.5px;
        }

        .bcl-notice-card.alert-notice {
            background: #fef2f2;
            border: 1px solid #fecaca;
            color: #991b1b;
        }
        .bcl-notice-card.alert-notice strong {
            color: #b91c1c;
            display: block;
            margin-bottom: 3px;
            font-size: 13.5px;
        }

        .bcl-notice-icon {
            font-size: 20px;
            flex-shrink: 0;
            margin-top: 1px;
        }

        .bcl-rules-checklist {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 14px 16px;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .bcl-rule-item {
            display: flex;
            align-items: flex-start;
            gap: 10px;
            font-size: 13px;
            color: #334155;
            line-height: 1.5;
        }

        .bcl-check-bullet {
            color: #059669;
            font-weight: 800;
            font-size: 14px;
            flex-shrink: 0;
        }

        .bcl-instruction-footer {
            padding: 16px 26px;
            background: #f8fafc;
            border-top: 1px solid #e2e8f0;
            display: flex;
            justify-content: flex-end;
        }

        .bcl-start-exam-btn {
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
            color: #ffffff;
            border: none;
            border-radius: 10px;
            padding: 12px 24px;
            font-size: 14px;
            font-weight: 700;
            cursor: pointer;
            box-shadow: 0 4px 14px rgba(79, 70, 229, 0.35);
            transition: all 0.15s ease;
        }
        .bcl-start-exam-btn:hover {
            background: linear-gradient(135deg, #4338ca 0%, #6d28d9 100%);
            transform: translateY(-1px);
            box-shadow: 0 6px 18px rgba(79, 70, 229, 0.45);
        }

        /* Exam Violation Warning Modal */
        #bcl-violation-modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(15, 23, 42, 0.82);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            z-index: 1000000;
            align-items: center;
            justify-content: center;
            padding: 16px;
            box-sizing: border-box;
            font-family: var(--font-sans) !important;
        }

        .bcl-violation-dialog {
            background: #ffffff;
            border-radius: 18px;
            max-width: 480px;
            width: 100%;
            box-shadow: 0 25px 50px -12px rgba(220, 38, 38, 0.28);
            border: 1px solid #fecaca;
            overflow: hidden;
            animation: bclFadeIn 0.2s ease-out;
            padding: 26px 28px;
            text-align: center;
        }

        .bcl-violation-icon {
            width: 54px;
            height: 54px;
            background: #fee2e2;
            color: #dc2626;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 26px;
            margin-bottom: 14px;
            border: 4px solid #fef2f2;
        }

        .bcl-violation-title {
            font-size: 17.5px;
            font-weight: 800;
            color: #991b1b;
            margin: 0 0 8px 0;
            line-height: 1.3;
        }

        .bcl-violation-message {
            font-size: 13.5px;
            color: #334155;
            line-height: 1.6;
            margin: 0 0 18px 0;
        }

        .bcl-violation-badge {
            display: inline-block;
            padding: 4px 12px;
            background: #fef2f2;
            border: 1px solid #fecaca;
            color: #b91c1c;
            font-size: 11.5px;
            font-weight: 700;
            border-radius: 9999px;
            margin-bottom: 14px;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        .bcl-violation-btn {
            width: 100%;
            padding: 11px 20px;
            background: #dc2626;
            color: #ffffff;
            font-family: var(--font-sans) !important;
            font-size: 14px;
            font-weight: 700;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            transition: background 0.15s ease, transform 0.15s ease;
            box-shadow: 0 4px 12px rgba(220, 38, 38, 0.3);
        }
        .bcl-violation-btn:hover {
            background: #b91c1c;
            transform: translateY(-1px);
        }
    </style>
    """

    # Website Exam Header HTML
    stage_pill = '<span class="bcl-stage-pill">Full Mock &bull; Stage 1/3 (Listening)</span>' if is_full_mock else '<span class="bcl-stage-pill">Listening Practice</span>'
    bcl_header_html = f"""
    <div id="bcl-exam-header">
        <div class="bcl-header-group">
            <a href="/dashboard/" class="bcl-back-link" id="bclHeaderBackBtn" onclick="event.preventDefault(); handleExitPrompt(); return false;" title="Exit to Candidate Dashboard">&larr; Dashboard</a>
            <div class="bcl-brand-badge">🎧</div>
            <div class="bcl-title-box">
                <span class="bcl-main-title">Test {mock_num}: {mock_test.title}</span>
                <span class="bcl-sub-meta">Module Attempt #{attempt.pk} &bull; {stage_pill}</span>
            </div>
        </div>

        <div class="bcl-header-group">
            <div class="bcl-timer-pill" title="Exam Timer">
                <span>⏱️</span>
                <span id="bclHeaderTimer">40:00</span>
            </div>
            <div class="bcl-user-badge">
                Candidate: <strong>{candidate_name}</strong>
            </div>
            <button type="button" class="bcl-info-btn" onclick="bclShowInstructions()" title="View Exam Instructions">
                ℹ️ Instructions
            </button>
        </div>

        <div class="bcl-header-group">
            <button type="button" class="bcl-submit-btn" id="bclHeaderSubmitBtn" onclick="bclConfirmAndSubmit()">
                Submit Listening &check;
            </button>
        </div>
    </div>
    """

    # Website Completion Modal Popup HTML
    next_btn_label = "Proceed to Reading Module &rarr;" if is_full_mock else "Return to Dashboard &rarr;"
    bcl_modal_html = f"""
    <div id="bcl-listening-modal">
        <div class="bcl-modal-container">
            <div class="bcl-modal-top">
                <div>
                    <span class="bcl-stage-pill">Listening Test Completed</span>
                    <h2 style="margin: 4px 0 0 0; font-size: 18px; font-weight: 800; color: #0f172a;">Exam Result &amp; Answers Review</h2>
                    <p style="margin: 3px 0 0 0; font-size: 12px; color: #64748b;">Candidate: <strong>{candidate_name} ({candidate_username})</strong> &bull; Test {mock_num}: {mock_test.title}</p>
                </div>
                <button type="button" onclick="bclCloseModal()" style="border:none;background:transparent;font-size:22px;cursor:pointer;color:#94a3b8;">&times;</button>
            </div>

            <div class="bcl-modal-score-banner">
                <div>
                    <div class="bcl-metric-title">Score</div>
                    <div class="bcl-metric-value" id="bclMetricScore">0 / 40</div>
                </div>
                <div class="bcl-metric-divider"></div>
                <div>
                    <div class="bcl-metric-title">IELTS Band</div>
                    <div class="bcl-metric-value" id="bclMetricBand">Band 0.0</div>
                </div>
                <div class="bcl-metric-divider"></div>
                <div>
                    <div class="bcl-metric-title">Status</div>
                    <div style="font-size: 14px; font-weight: 700; color: #059669; margin-top: 4px;">Saved to Database &check;</div>
                </div>
            </div>

            <div class="bcl-modal-table-scroll">
                <table class="bcl-review-table">
                    <thead>
                        <tr>
                            <th style="width: 60px;">Q#</th>
                            <th>Your Answer</th>
                            <th>Correct Answer</th>
                            <th style="width: 100px;">Status</th>
                        </tr>
                    </thead>
                    <tbody id="bclReviewTableBody">
                    </tbody>
                </table>
            </div>

            <div class="bcl-modal-bottom">
                <button type="button" class="bcl-back-link" onclick="bclCloseModal()">Review on Page</button>
                <button type="button" class="bcl-submit-btn" id="bclModalNextBtn" onclick="window.location.href=(window.__bclConfirmedNextUrl || '{next_url}')">
                    {next_btn_label}
                </button>
            </div>
        </div>
    </div>
    """

    # Initial Entry Instructions Modal HTML
    bcl_instruction_modal_html = f"""
    <div id="bcl-instruction-modal">
        <div class="bcl-instruction-dialog">
            <div class="bcl-instruction-header">
                <div class="bcl-instruction-icon-badge">🎧</div>
                <div>
                    <span class="bcl-stage-pill">Official Exam Guidelines</span>
                    <h2 class="bcl-instruction-title">IELTS Academic Listening Instructions</h2>
                    <p class="bcl-instruction-sub">Test {mock_num}: {mock_test.title} &bull; 40 Questions &bull; 40 Minutes</p>
                </div>
            </div>

            <div class="bcl-instruction-body">
                <!-- Audio Notice Box -->
                <div class="bcl-notice-card audio-notice">
                    <div class="bcl-notice-icon">🔊</div>
                    <div class="bcl-notice-content">
                        <strong>Continuous Audio Recording (All 4 Sections Merge &amp; Play ONCE)</strong>
                        <div>The listening recording plays continuously from Section 1 through Section 4. Once started, <strong>it cannot be paused, rewound, or stopped</strong>. You can navigate between test parts at any time without interrupting the recording.</div>
                    </div>
                </div>

                <!-- Tab Switching Warning Notice Box -->
                <div class="bcl-notice-card alert-notice">
                    <div class="bcl-notice-icon">⚠️</div>
                    <div class="bcl-notice-content">
                        <strong>Exam Integrity &amp; Anti-Cheat Policy</strong>
                        <div>You must remain on this browser tab throughout the examination. <strong>Leaving this tab or switching windows triggers an Exam Integrity Warning.</strong> A maximum of 2 warnings are permitted; on the <strong>3rd violation, your exam will be automatically submitted and ended immediately</strong>.</div>
                    </div>
                </div>

                <!-- Key Instructions List -->
                <div class="bcl-rules-checklist">
                    <div class="bcl-rule-item">
                        <span class="bcl-check-bullet">&check;</span>
                        <span><strong>4 Test Parts:</strong> Answer Questions 1&ndash;40 as you listen to the recording.</span>
                    </div>
                    <div class="bcl-rule-item">
                        <span class="bcl-check-bullet">&check;</span>
                        <span><strong>Strict Word Limits:</strong> Read instructions for each question carefully (e.g. <em>ONE WORD ONLY</em> or <em>NO MORE THAN TWO WORDS</em>).</span>
                    </div>
                    <div class="bcl-rule-item">
                        <span class="bcl-check-bullet">&check;</span>
                        <span><strong>40-Minute Server Timer:</strong> The countdown starts immediately. Refreshing the browser does not pause your exam timer or audio.</span>
                    </div>
                    <div class="bcl-rule-item">
                        <span class="bcl-check-bullet">&check;</span>
                        <span><strong>Official Submission:</strong> When finished, click <em>Submit Listening &check;</em> in the top header to save your test and review your answers.</span>
                    </div>
                </div>
            </div>

            <div class="bcl-instruction-footer">
                <button type="button" class="bcl-start-exam-btn" id="bclStartExamBtn" onclick="bclDismissInstructions()">
                    I Understand &mdash; Start Listening Examination &rarr;
                </button>
            </div>
        </div>
    </div>
    """

    # Exam Violation Warning Modal HTML
    bcl_violation_modal_html = """
    <div id="bcl-violation-modal" role="alertdialog" aria-modal="true" aria-labelledby="bclViolationTitle" aria-describedby="bclViolationMessage">
        <div class="bcl-violation-dialog">
            <div class="bcl-violation-icon">⚠️</div>
            <span class="bcl-violation-badge" id="bclViolationBadge">Exam Integrity Warning</span>
            <h2 class="bcl-violation-title" id="bclViolationTitle">Exam Integrity Warning</h2>
            <p class="bcl-violation-message" id="bclViolationMessage">
                You left the examination window or switched browser tabs. Switching tabs a total of 3 times will automatically submit and end your exam!
            </p>
            <button type="button" class="bcl-violation-btn" id="bclAcknowledgeViolation" onclick="bclDismissViolation()">
                I understand &mdash; Return to exam
            </button>
        </div>
    </div>
    """

    # Client-Side Bridge JavaScript with Continuous Multi-Section Audio Engine
    bcl_bridge_js = f"""
    <script>
    (function() {{
        const attemptId = {attempt.pk};
        const mockId = {mock_id};
        const isFullMock = {'true' if is_full_mock else 'false'};
        const submitUrl = "{submit_url}";
        const nextUrl = "{next_url}";
        const violationUrl = "{violation_url}";
        const endedUrl = "{ended_url}";
        const csrfToken = "{csrf_token}";
        let alreadySubmitted = false;

        // Authoritative 40-Minute Timer
        const serverAnswerKey = {server_answer_key_json};
        let timeRemaining = {remaining_seconds};
        if (!timeRemaining || timeRemaining <= 0 || isNaN(timeRemaining)) {{
            timeRemaining = 40 * 60;
        }}

        function formatTimerString(totalSec) {{
            const m = Math.floor(Math.max(0, totalSec) / 60);
            const s = Math.max(0, totalSec) % 60;
            return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
        }}

        function syncAllTimers() {{
            const timeStr = formatTimerString(timeRemaining);
            const hTimer = document.getElementById('bclHeaderTimer');
            if (hTimer) {{
                hTimer.textContent = timeStr;
                if (timeRemaining <= 300) {{
                    hTimer.style.color = '#dc2626';
                    hTimer.classList.add('warning');
                }} else {{
                    hTimer.style.color = '#1e293b';
                    hTimer.classList.remove('warning');
                }}
            }}

            const timerSelectors = [
                '.timer-display', '#timer-text', '#timerDisplay', '#timer', 
                '.timer-time', '#time-left', '.time-left', '#timeDisplay', 
                '#countdown', '.countdown', '#exam-timer', '.exam-timer'
            ];
            timerSelectors.forEach(function(sel) {{
                document.querySelectorAll(sel).forEach(function(el) {{
                    el.textContent = timeStr;
                    if (timeRemaining <= 300) el.style.color = '#dc2626';
                }});
            }});
        }}

        syncAllTimers();

        const bclTimerInterval = setInterval(function() {{
            if (timeRemaining > 0) {{
                timeRemaining--;
                syncAllTimers();
            }} else {{
                clearInterval(bclTimerInterval);
                timeRemaining = 0;
                syncAllTimers();
                alert("Time is up (40 minutes)! Your listening answers are being submitted.");
                bclTriggerSubmission();
            }}
        }}, 1000);

        window.toggleTimer = function() {{}};
        window.startTimer = function() {{}};

        // Instruction Modal Controls
        function bclDismissInstructions() {{
            const m = document.getElementById('bcl-instruction-modal');
            if (m) m.style.display = 'none';
        }}
        window.bclDismissInstructions = bclDismissInstructions;

        function bclShowInstructions() {{
            const m = document.getElementById('bcl-instruction-modal');
            if (m) m.style.display = 'flex';
        }}
        window.bclShowInstructions = bclShowInstructions;

        // =========================================================================
        // UNIVERSAL CONTINUOUS AUDIO ENGINE: ALL 4 SECTIONS MERGE & PLAY SEAMLESSLY
        // =========================================================================
        const audioStorageKey = 'bcl_listening_audio_attempt_' + attemptId;
        const mergedAudioUrl = "{merged_audio_url}";
        window.__bclAllowSubmissionPause = false;

        // Detect all audio elements on page
        const audioElements = [];
        for (let i = 1; i <= 4; i++) {{
            const el = document.getElementById('audio' + i);
            if (el) audioElements.push(el);
        }}
        const masterSingleAudio = document.getElementById('mainAudio') 
            || document.getElementById('global-audio-player') 
            || document.getElementById('audio1') 
            || document.querySelector('audio');

        if (masterSingleAudio && mergedAudioUrl) {{
            masterSingleAudio.src = mergedAudioUrl;
            masterSingleAudio.preload = 'auto';
        }}

        if (audioElements.length === 0 && masterSingleAudio) {{
            audioElements.push(masterSingleAudio);
        }}

        let activeTrackIndex = 0;
        let isMasterPlaying = false;

        // Setup loadedmetadata to guarantee progress bar displays the full combined duration!
        if (masterSingleAudio) {{
            function updateMasterDurationUI() {{
                if (masterSingleAudio.duration && !isNaN(masterSingleAudio.duration)) {{
                    const progressBar = document.getElementById('progress-bar') || document.querySelector('.progress-bar');
                    const totalDurationEl = document.getElementById('total-duration') || document.querySelector('.total-duration');
                    if (progressBar) progressBar.max = masterSingleAudio.duration;
                    if (totalDurationEl) {{
                        const m = Math.floor(masterSingleAudio.duration / 60);
                        const s = Math.floor(masterSingleAudio.duration % 60);
                        totalDurationEl.textContent = (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
                    }}
                }}
            }}
            masterSingleAudio.addEventListener('loadedmetadata', updateMasterDurationUI);
            masterSingleAudio.addEventListener('durationchange', updateMasterDurationUI);
            masterSingleAudio.addEventListener('canplay', updateMasterDurationUI);
        }}

        function updateAllPlayButtonsUI(isPlaying) {{
            isMasterPlaying = isPlaying;
            const playBtns = document.querySelectorAll('#audioPlay, #play-pause-btn, .audio-play, .audio-btn-play, #btnAudioPlay, #btnPlayPause, #audio-play-btn');
            playBtns.forEach(function(btn) {{
                if (isPlaying) {{
                    btn.innerHTML = '<span style="display:inline-flex;align-items:center;gap:6px;"><span class="audio-wave-bars playing"><span></span><span></span><span></span><span></span></span> Playing 🎧</span>';
                    btn.classList.add('playing');
                    btn.title = 'IELTS Listening audio cannot be paused during the examination.';
                    btn.style.cursor = 'default';
                }} else {{
                    btn.innerHTML = '&#9654; Start Listening Audio';
                    btn.classList.remove('playing');
                    btn.style.cursor = 'pointer';
                }}
            }});
        }}

        function lockAudioContinuous(audio) {{ lockAudioElement(audio); }}
        function lockAudioElement(audio) {{
            if (!audio || audio.__bclLocked) return;
            audio.__bclLocked = true;

            const origPause = HTMLMediaElement.prototype.pause;
            audio.pause = function() {{
                if (window.__bclAllowSubmissionPause) {{
                    origPause.call(audio);
                }} else {{
                    console.warn("BCL IELTS Engine: Continuous audio playback cannot be paused.");
                }}
            }};

            audio.addEventListener('play', function() {{
                let state = null;
                try {{ state = JSON.parse(localStorage.getItem(audioStorageKey) || '{{}}'); }} catch(e) {{}}
                if (!state || !state.is_started) {{
                    state = {{
                        is_started: true,
                        track_index: activeTrackIndex,
                        start_epoch: Date.now() - (audio.currentTime * 1000)
                    }};
                    localStorage.setItem(audioStorageKey, JSON.stringify(state));
                }}
                updateAllPlayButtonsUI(true);
            }});

            audio.addEventListener('timeupdate', function() {{
                try {{
                    let state = JSON.parse(localStorage.getItem(audioStorageKey) || '{{}}');
                    state.is_started = true;
                    state.track_index = activeTrackIndex;
                    state.last_pos = audio.currentTime;
                    if (!state.start_epoch) {{
                        state.start_epoch = Date.now() - (audio.currentTime * 1000);
                    }}
                    localStorage.setItem(audioStorageKey, JSON.stringify(state));
                }} catch(e) {{}}
            }});
        }}

        // Setup all audio tags
        audioElements.forEach(lockAudioElement);
        if (masterSingleAudio) lockAudioElement(masterSingleAudio);

        // Chain multiple audio tracks: Section 1 -> Section 2 -> Section 3 -> Section 4 (Mocks 22, 24-29)
        if (audioElements.length > 1) {{
            for (let i = 0; i < audioElements.length; i++) {{
                (function(idx) {{
                    const aud = audioElements[idx];
                    aud.addEventListener('ended', function() {{
                        if (idx + 1 < audioElements.length) {{
                            activeTrackIndex = idx + 1;
                            const nextAud = audioElements[activeTrackIndex];
                            if (nextAud) {{
                                nextAud.currentTime = 0;
                                nextAud.play();
                            }}
                        }}
                    }});
                }})(i);
            }}
        }}

        // Chain audioSources object (Mocks 2 & 18: audioSources = {{ 1: ..., 2: ..., 3: ..., 4: ... }})
        let currentSourcePart = 1;
        if (masterSingleAudio) {{
            masterSingleAudio.addEventListener('ended', function() {{
                if (typeof window.audioSources === 'object' && currentSourcePart < 4) {{
                    currentSourcePart++;
                    if (window.audioSources[currentSourcePart]) {{
                        masterSingleAudio.src = window.audioSources[currentSourcePart];
                        masterSingleAudio.currentTime = 0;
                        masterSingleAudio.play();
                    }}
                }}
            }});
        }}

        // NEUTRALIZE INTERNAL PART SWITCHERS: Changing tabs NEVER stops audio!
        const origSwitchToPart = window.switchToPart;
        window.switchToPart = function(partNumber) {{
            const aud = masterSingleAudio || document.querySelector('audio');
            const wasPlaying = aud && !aud.paused;
            const curTime = aud ? aud.currentTime : 0;
            const curSrc = aud ? aud.src : '';

            // Switch question panels in DOM
            document.querySelectorAll('.question-part, [id^="part-"]').forEach(part => part.classList.add('hidden'));
            const partToShow = document.getElementById('part-' + partNumber);
            if (partToShow) partToShow.classList.remove('hidden');

            // Update footer question wrappers
            document.querySelectorAll('.footer__questionWrapper___1tZ46, .section-tab, .nav-tab').forEach((wrapper, index) => {{
                if (index === partNumber - 1) wrapper.classList.add('selected', 'active');
                else wrapper.classList.remove('selected', 'active');
            }});

            try {{
                if (origSwitchToPart) {{
                    const origPause = aud ? aud.pause : null;
                    if (aud) aud.pause = function() {{}};
                    origSwitchToPart(partNumber, false);
                    if (aud && origPause) aud.pause = origPause;
                }}
            }} catch(e) {{}}

            // Ensure single continuous audio remained intact
            if (aud) {{
                if (mergedAudioUrl && !aud.src.endsWith(mergedAudioUrl)) {{
                    aud.src = mergedAudioUrl;
                    aud.currentTime = curTime;
                }} else if (curSrc && aud.src !== curSrc) {{
                    aud.src = curSrc;
                    aud.currentTime = curTime;
                }}
                if (wasPlaying && aud.paused) {{
                    aud.currentTime = curTime;
                    aud.play().catch(function() {{}});
                }}
            }}
        }};

        const origSwitchToSection = window.switchToSection;
        window.switchToSection = function(n) {{
            const aud = masterSingleAudio || document.querySelector('audio');
            const wasPlaying = aud && !aud.paused;
            const curTime = aud ? aud.currentTime : 0;
            const curSrc = aud ? aud.src : '';

            for (let i = 1; i <= 4; i++) {{
                const p = document.getElementById('section' + i + '-panel');
                if (p) {{
                    if (i === n) p.classList.remove('hidden');
                    else p.classList.add('hidden');
                }}
                const t = document.getElementById('tab' + i);
                if (t) {{
                    if (i === n) t.classList.add('active');
                    else t.classList.remove('active');
                }}
            }}

            try {{
                if (origSwitchToSection) {{
                    const origPause = aud ? aud.pause : null;
                    if (aud) aud.pause = function() {{}};
                    origSwitchToSection(n);
                    if (aud && origPause) aud.pause = origPause;
                }}
            }} catch(e) {{}}

            if (aud) {{
                if (mergedAudioUrl && !aud.src.endsWith(mergedAudioUrl)) {{
                    aud.src = mergedAudioUrl;
                    aud.currentTime = curTime;
                }} else if (curSrc && aud.src !== curSrc) {{
                    aud.src = curSrc;
                    aud.currentTime = curTime;
                }}
                if (wasPlaying && aud.paused) {{
                    aud.currentTime = curTime;
                    aud.play().catch(function() {{}});
                }}
            }}
        }};

        function startMasterPlayback() {{
            const aud = masterSingleAudio || audioElements[0];
            if (aud) {{
                if (mergedAudioUrl && !aud.src.endsWith(mergedAudioUrl)) {{
                    aud.src = mergedAudioUrl;
                }}
                aud.play().then(function() {{
                    updateAllPlayButtonsUI(true);
                }}).catch(function(e) {{
                    console.warn("Audio play error:", e);
                }});
            }}
        }}

        function showAutoplayResumePill(targetPos, trackIdx) {{
            if (document.getElementById('bclAudioResumeBanner')) return;
            const banner = document.createElement('div');
            banner.id = 'bclAudioResumeBanner';
            banner.style.cssText = 'position:fixed; top:66px; left:50%; transform:translateX(-50%); z-index:100000; background:linear-gradient(135deg, #4f46e5, #7c3aed); color:#fff; padding:8px 22px; border-radius:9999px; font-weight:700; font-size:13.5px; box-shadow:0 8px 24px rgba(79,70,229,0.35); cursor:pointer; display:flex; align-items:center; gap:8px; animation:bclAudioPulse 1.5s infinite alternate;';
            banner.innerHTML = '<span>🎧 Listening Audio in Progress &bull; Click anywhere to resume audio</span>';

            const resumeAction = function() {{
                const targetAud = (audioElements.length > 1 && trackIdx < audioElements.length) ? audioElements[trackIdx] : masterSingleAudio;
                if (targetAud) {{
                    if (targetPos && !isNaN(targetPos)) targetAud.currentTime = targetPos;
                    targetAud.play();
                }}
                if (banner && banner.parentNode) banner.parentNode.removeChild(banner);
                document.removeEventListener('click', resumeAction);
            }};

            banner.addEventListener('click', resumeAction);
            document.addEventListener('click', resumeAction, {{ once: true }});
            document.body.appendChild(banner);
        }}

        function initAudioEngine() {{
            // Browser Back/Forward means a new listening visit; restart at 00:00.
            // A normal reload retains the existing exam playback continuity.
            const navigation = performance.getEntriesByType('navigation')[0];
            const returnedByBack = navigation && navigation.type === 'back_forward';
            if (returnedByBack) localStorage.removeItem(audioStorageKey);
            let state = null;
            try {{ state = JSON.parse(localStorage.getItem(audioStorageKey) || '{{}}'); }} catch(e) {{}}

            if (state && state.is_started) {{
                const trackIdx = state.track_index || 0;
                activeTrackIndex = trackIdx;
                const elapsed = Math.max(0, (Date.now() - (state.start_epoch || Date.now())) / 1000);
                const aud = (audioElements.length > 1 && trackIdx < audioElements.length) ? audioElements[trackIdx] : masterSingleAudio;

                if (aud) {{
                    const targetPos = (elapsed > 0 && elapsed < (aud.duration || 3600)) ? elapsed : (state.last_pos || 0);
                    const tryResume = function() {{
                        try {{
                            if (targetPos && !isNaN(targetPos)) aud.currentTime = targetPos;
                            const p = aud.play();
                            if (p && p.catch) p.catch(() => showAutoplayResumePill(targetPos, trackIdx));
                        }} catch(e) {{
                            showAutoplayResumePill(targetPos, trackIdx);
                        }}
                    }};

                    if (aud.readyState >= 1) tryResume();
                    else {{
                        aud.addEventListener('loadedmetadata', tryResume, {{ once: true }});
                        aud.addEventListener('canplay', tryResume, {{ once: true }});
                        setTimeout(tryResume, 600);
                    }}
                }}
            }} else {{
                // Fresh attempt start: Show instruction modal and start audio from 0:00
                bclShowInstructions();
            }}

            // Intercept ALL play button clicks
            const playBtns = document.querySelectorAll('#audioPlay, #play-pause-btn, .audio-play, .audio-btn-play, #btnAudioPlay, #btnPlayPause, #audio-play-btn');
            playBtns.forEach(function(btn) {{
                btn.addEventListener('click', function(e) {{
                    if (isMasterPlaying) {{
                        e.preventDefault();
                        e.stopPropagation();
                        return false;
                    }}
                    startMasterPlayback();
                }}, true);
            }});

            window.toggleAudio = startMasterPlayback;
        }}

        initAudioEngine();
        window.addEventListener('pageshow', function(event) {{
            if (!event.persisted) return;
            localStorage.removeItem(audioStorageKey);
            activeTrackIndex = 0;
            audioElements.forEach(function(audio) {{
                try {{ HTMLMediaElement.prototype.pause.call(audio); audio.currentTime = 0; }} catch(e) {{}}
            }});
            isMasterPlaying = false;
            updateAllPlayButtonsUI(false);
            bclShowInstructions();
        }});

        // =========================================================================
        // EXAM INTEGRITY & TAB SWITCHING VIOLATION MONITORING
        // =========================================================================
        let finishing = false;
        let violationPending = false;
        let lastViolationAt = 0;
        let warningOpen = false;

        async function reportViolation(reason) {{
            if (finishing || violationPending || alreadySubmitted) return;
            const now = Date.now();
            if (now - lastViolationAt < 3000) return;
            lastViolationAt = now;
            violationPending = true;

            let extractedAnswers = null;
            try {{ extractedAnswers = extractAnswersAndScore(); }} catch(e) {{}}

            const reqPayload = {{ reason: reason }};
            if (extractedAnswers) {{
                reqPayload.raw_score = extractedAnswers.score;
                reqPayload.answers_payload = {{
                    score: extractedAnswers.score,
                    total: 40,
                    band_score: calculateBand(extractedAnswers.score),
                    answers: extractedAnswers.answers
                }};
            }}

            try {{
                const response = await fetch(violationUrl, {{
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {{
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken,
                        'X-Requested-With': 'XMLHttpRequest',
                    }},
                    body: JSON.stringify(reqPayload),
                    keepalive: true,
                }});

                const data = await response.json().catch(() => ({{}}));

                if (response.status === 409 || data.status === 'auto_submitted' || data.auto_submitted) {{
                    finishing = true;
                    alreadySubmitted = true;
                    window.__bclAllowSubmissionPause = true;
                    audioElements.forEach(a => {{ try {{ HTMLMediaElement.prototype.pause.call(a); }} catch(e) {{}} }});
                    localStorage.removeItem(audioStorageKey);

                    const dest = data.redirect_url || endedUrl || '/dashboard/';
                    alert("Exam Auto-Submitted: You exceeded the allowed tab-switching violations. Your examination has been automatically submitted.");
                    window.location.replace(dest);
                    return;
                }}

                if (data.warning) {{
                    warningOpen = true;
                    const vModal = document.getElementById('bcl-violation-modal');
                    const vTitle = document.getElementById('bclViolationTitle');
                    const vMsg = document.getElementById('bclViolationMessage');
                    const vBadge = document.getElementById('bclViolationBadge');

                    if (vTitle && data.warning_title) vTitle.textContent = data.warning_title;
                    if (vMsg && data.warning_message) vMsg.textContent = data.warning_message;
                    if (vBadge) vBadge.textContent = "Warning " + (data.violation_count || 1) + " of " + ((data.max_violations || 3) - 1);

                    if (vModal) vModal.style.display = 'flex';
                    const ackBtn = document.getElementById('bclAcknowledgeViolation');
                    if (ackBtn) ackBtn.focus();
                }}
            }} catch(err) {{
                console.warn('Could not record tab violation:', err);
            }} finally {{
                violationPending = false;
            }}
        }}

        function bclDismissViolation() {{
            const vModal = document.getElementById('bcl-violation-modal');
            if (vModal) vModal.style.display = 'none';
            warningOpen = false;
            lastViolationAt = 0;
        }}
        window.bclDismissViolation = bclDismissViolation;

        document.addEventListener('visibilitychange', function() {{
            if (document.hidden) reportViolation('tab_hidden');
            else if (warningOpen) {{
                const ackBtn = document.getElementById('bclAcknowledgeViolation');
                if (ackBtn) ackBtn.focus();
            }}
        }});

        window.addEventListener('blur', function() {{
            setTimeout(function() {{
                if (!document.hidden && !warningOpen && !document.hasFocus()) {{
                    reportViolation('window_blur');
                }}
            }}, 500);
        }});

        // =========================================================================
        // OFFICIAL SUBMISSION & RESULTS
        // =========================================================================
        function hideAllLegacyModals() {{
            try {{
                const legacy = document.querySelectorAll(
                    '#resultsModal, #result-modal, #results-modal, [id*="result-modal"], [id*="results-modal"], [id*="resultsModal"], .modal-overlay:not(#bcl-listening-modal):not(#bcl-instruction-modal):not(#bcl-violation-modal), .modal:not(#bcl-listening-modal):not(#bcl-instruction-modal):not(#bcl-violation-modal)'
                );
                legacy.forEach(function(el) {{
                    el.style.setProperty('display', 'none', 'important');
                    el.style.setProperty('visibility', 'hidden', 'important');
                    el.classList.remove('show');
                    el.setAttribute('aria-hidden', 'true');
                }});
            }} catch(e) {{}}
        }}

        window.bclCloseModal = function() {{
            const m = document.getElementById('bcl-listening-modal');
            if (m) m.style.display = 'none';
            hideAllLegacyModals();
        }};

        let isBclSubmitting = false;
        const origPageCheckAnswers = window.checkAnswers;

        window.bclConfirmAndSubmit = function() {{
            if (alreadySubmitted || isBclSubmitting) return;
            const msg = isFullMock
                ? "Are you sure you want to submit Listening and proceed to the Reading module? You cannot change Listening answers after submitting."
                : "Are you sure you want to submit your examination? You cannot modify answers after submitting.";
            if (window.confirm(msg)) {{
                window.bclTriggerSubmission(false);
            }}
        }};

        window.bclTriggerSubmission = function(isExit = false) {{
            if (alreadySubmitted || isBclSubmitting) return;
            isBclSubmitting = true;
            // Run page grader first so #result-details / #resultsTable are populated
            if (typeof origPageCheckAnswers === 'function') {{
                try {{ origPageCheckAnswers(); }} catch(e) {{}}
            }} else if (typeof window.checkAnswers === 'function' && window.checkAnswers !== bclCheckAnswersHook) {{
                try {{ window.checkAnswers(); }} catch(e) {{}}
            }}
            hideAllLegacyModals();
            const extracted = extractAnswersAndScore();
            submitToBackend(extracted, isExit);
        }};

        function bclCheckAnswersHook() {{
            if (origPageCheckAnswers) {{
                try {{ origPageCheckAnswers.apply(this, arguments); }} catch(e) {{}}
            }}
            hideAllLegacyModals();
            if (!alreadySubmitted && !isBclSubmitting) {{
                window.bclTriggerSubmission(false);
            }}
        }}
        window.checkAnswers = bclCheckAnswersHook;

        // Suppress legacy opener functions so they never pop up raw modals
        window.showResultsModal = function() {{ hideAllLegacyModals(); }};

        function extractAnswersAndScore() {{
            let score = 0;
            let answers = {{}};

            // Extract score from raw DOM if computed
            const scoreSum = document.getElementById('resultsSummary') || document.getElementById('score-summary') || document.getElementById('scoreSummary');
            if (scoreSum && scoreSum.textContent) {{
                const m = scoreSum.textContent.match(/(\d+)\s*(?:out of|\/)\s*40/i);
                if (m) score = parseInt(m[1], 10);
            }}
            const resScore = document.getElementById('resScore') || document.getElementById('res-total-score');
            if (!score && resScore && resScore.textContent) {{
                const m = resScore.textContent.match(/(\d+)/);
                if (m) score = parseInt(m[1], 10);
            }}
            if (!score) {{
                if (typeof window.totalCorrect !== 'undefined') score = window.totalCorrect;
                else if (typeof window.score !== 'undefined') score = window.score;
            }}

            // Pattern A: #resultsTable .result-row (Vol 3 format)
            const vol3Rows = document.querySelectorAll('#resultsTable .result-row');
            if (vol3Rows.length > 0) {{
                vol3Rows.forEach(function(row) {{
                    const qEl = row.querySelector('.q-num') || row.children[0];
                    const uEl = row.querySelector('.user-ans') || row.children[1];
                    const cEl = row.querySelector('.correct-ans') || row.children[2];
                    const sEl = row.querySelector('.result-status') || row.children[3];
                    if (qEl && uEl && cEl) {{
                        const qNum = qEl.textContent.trim();
                        const uAns = uEl.textContent.trim();
                        const cAns = cEl.textContent.trim();
                        const isCor = row.classList.contains('correct') 
                            || row.getAttribute('data-correct') === '1'
                            || row.getAttribute('data-score') === '1'
                            || (sEl && sEl.textContent.includes('✓'));
                        answers[qNum] = {{ "user_answer": uAns, "correct_answer": cAns, "is_correct": isCor }};
                    }}
                }});
            }}

            // Pattern B: #result-details table (Mock 1-21 format)
            if (Object.keys(answers).length === 0) {{
                const tableRows = document.querySelectorAll('#result-details tr, .result-details tr');
                if (tableRows.length > 1) {{
                    for (let i = 1; i < tableRows.length; i++) {{
                        const cols = tableRows[i].querySelectorAll('td');
                        if (cols.length >= 4) {{
                            const qNum = cols[0].textContent.trim();
                            const uAns = cols[1].textContent.trim();
                            const cAns = cols[2].textContent.trim();
                            const isCor = cols[3].classList.contains('result-correct') || cols[3].textContent.includes('✓') || cols[3].textContent.includes('Correct');
                            answers[qNum] = {{ "user_answer": uAns, "correct_answer": cAns, "is_correct": isCor }};
                        }}
                    }}
                }}
            }}

            // Pattern C: #resultsTableBody or #res-table-body (Mocks 22-29)
            if (Object.keys(answers).length === 0) {{
                const modernRows = document.querySelectorAll('#resultsTableBody .result-row, #res-table-body .result-row');
                if (modernRows.length > 0) {{
                    modernRows.forEach(function(row) {{
                        const qEl = row.querySelector('.res-q-num, .q-num') || row.children[0];
                        const uEl = row.querySelector('.res-user-ans, .user-ans') || row.children[1];
                        const cEl = row.querySelector('.res-correct-ans, .correct-ans') || row.children[2];
                        const sEl = row.querySelector('.res-status, .result-status') || row.children[3];
                        if (qEl) {{
                            const qNum = qEl.textContent.replace(/[^0-9]/g, '').trim();
                            const uAns = uEl ? uEl.textContent.trim() : '';
                            const cAns = cEl ? cEl.textContent.trim() : '';
                            const isCor = row.classList.contains('correct')
                                || row.getAttribute('data-correct') === '1'
                                || (sEl && (sEl.textContent.includes('✓') || sEl.textContent.toLowerCase().includes('correct')));
                            if (qNum) answers[qNum] = {{ "user_answer": uAns, "correct_answer": cAns, "is_correct": isCor }};
                        }}
                    }});
                }}
            }}

            // Authoritative Completion & Normalization: Ensure all Q1-40 have genuine correct answers (never '-')
            for (let i = 1; i <= 40; i++) {{
                const k = String(i);
                let uAns = '';
                if (answers[k] && answers[k].user_answer) {{
                    uAns = answers[k].user_answer.trim();
                }}
                // Check range keys in answers like '11-12' or '13-14'
                if (!uAns) {{
                    for (const aKey of Object.keys(answers)) {{
                        if (aKey.includes('-')) {{
                            const parts = aKey.split('-').map(x => parseInt(x.replace(/[^0-9]/g, ''), 10));
                            if (parts.length === 2 && i >= parts[0] && i <= parts[1]) {{
                                const rangeItem = answers[aKey];
                                if (rangeItem && rangeItem.user_answer) {{
                                    const vals = rangeItem.user_answer.split(',').map(s => s.trim());
                                    const offset = i - parts[0];
                                    uAns = vals[offset] || rangeItem.user_answer;
                                    break;
                                }}
                            }}
                        }}
                    }}
                }}
                if (!uAns) {{
                    const input = document.getElementById('q' + i)
                        || document.querySelector('input[name="q' + i + '"]:checked')
                        || document.querySelector('input[name="q' + i + '"]')
                        || document.querySelector('select[name="q' + i + '"]');
                    if (input) uAns = (input.value || '').trim();
                }}
                if (!uAns) {{
                    const checkedCbs = Array.from(document.querySelectorAll('input[type="checkbox"]:checked')).filter(cb => {{
                        const name = cb.name || cb.id || '';
                        const m = name.match(/q?(\d+)[-_](\d+)/);
                        if (m) {{
                            const s = parseInt(m[1], 10), e = parseInt(m[2], 10);
                            return i >= s && i <= e;
                        }}
                        return false;
                    }});
                    if (checkedCbs.length > 0) {{
                        uAns = checkedCbs.map(cb => cb.value.trim()).join(', ');
                    }}
                }}
                if (!uAns) {{
                    const dropZone = document.querySelector('[data-question="' + i + '"], [data-q="' + i + '"], #drop-' + i + ', #drop-zone-' + i + ', #drop_' + i);
                    if (dropZone) {{
                        uAns = (dropZone.textContent || dropZone.innerText || '').trim();
                    }}
                }}

                // Determine official correct answer from serverAnswerKey
                const rawKey = serverAnswerKey[k] || serverAnswerKey['q' + k] || '';
                let displayCorrect = '';
                let validOptions = [];

                if (Array.isArray(rawKey)) {{
                    displayCorrect = rawKey.join(' / ');
                    validOptions = rawKey.map(x => String(x).trim().toLowerCase());
                }} else if (typeof rawKey === 'string') {{
                    displayCorrect = rawKey;
                    if (rawKey.includes('/')) {{
                        rawKey.split('/').forEach(x => validOptions.push(x.trim().toLowerCase()));
                    }}
                    if (rawKey.includes('||')) {{
                        rawKey.split('||').forEach(x => validOptions.push(x.trim().toLowerCase()));
                    }}
                    if (rawKey.includes(',')) {{
                        rawKey.split(',').forEach(x => validOptions.push(x.trim().toLowerCase()));
                    }}
                    validOptions.push(rawKey.trim().toLowerCase());
                }}

                let cAns = (answers[k] && answers[k].correct_answer && answers[k].correct_answer !== '-') 
                    ? answers[k].correct_answer 
                    : displayCorrect;

                let isCor = false;
                if (answers[k] && typeof answers[k].is_correct === 'boolean') {{
                    isCor = answers[k].is_correct;
                }}
                const uNorm = uAns.toLowerCase().replace(/\s+/g, ' ').trim();
                if (!isCor && uNorm && validOptions.length > 0) {{
                    isCor = validOptions.some(opt => {{
                        const optNorm = opt.toLowerCase().replace(/\s+/g, ' ').trim();
                        return uNorm === optNorm;
                    }});
                }}

                answers[k] = {{
                    "user_answer": uAns,
                    "correct_answer": cAns,
                    "is_correct": isCor
                }};
            }}

            // Calculate overall score from all 40 questions
            let evaluatedScore = 0;
            for (let i = 1; i <= 40; i++) {{
                if (answers[String(i)] && answers[String(i)].is_correct) {{
                    evaluatedScore++;
                }}
            }}
            score = Math.max(score, evaluatedScore);

            return {{ score: score, answers: answers }};
        }}

        function calculateBand(score) {{
            if (score >= 39) return "9.0";
            if (score >= 37) return "8.5";
            if (score >= 35) return "8.0";
            if (score >= 32) return "7.5";
            if (score >= 30) return "7.0";
            if (score >= 26) return "6.5";
            if (score >= 23) return "6.0";
            if (score >= 18) return "5.5";
            if (score >= 16) return "5.0";
            if (score >= 13) return "4.5";
            if (score >= 11) return "4.0";
            if (score >= 8) return "3.5";
            if (score >= 6) return "3.0";
            if (score >= 4) return "2.5";
            if (score >= 3) return "2.0";
            if (score >= 2) return "1.5";
            if (score >= 1) return "1.0";
            return "0.0";
        }}

        function displayBclModal(score, band, answers) {{
            const modal = document.getElementById('bcl-listening-modal');
            const metricScore = document.getElementById('bclMetricScore');
            const metricBand = document.getElementById('bclMetricBand');
            const tableBody = document.getElementById('bclReviewTableBody');

            if (metricScore) metricScore.textContent = score + " / 40";
            if (metricBand) metricBand.textContent = "Band " + band;

            if (tableBody) {{
                let rowsHtml = '';
                const keys = Object.keys(answers).sort((a, b) => (parseInt(a, 10) || 0) - (parseInt(b, 10) || 0));

                keys.forEach(function(k) {{
                    const item = answers[k];
                    const isCor = item.is_correct;
                    rowsHtml += '<tr>';
                    rowsHtml += '<td><strong>' + k + '</strong></td>';
                    rowsHtml += '<td>' + (item.user_answer || '<em style="color:#94a3b8;">No Answer</em>') + '</td>';
                    rowsHtml += '<td><strong>' + (item.correct_answer || '-') + '</strong></td>';
                    rowsHtml += '<td><span class="bcl-status-pill ' + (isCor ? 'correct' : 'incorrect') + '">' + (isCor ? '✓ Correct' : '✗ Incorrect') + '</span></td>';
                    rowsHtml += '</tr>';
                }});

                tableBody.innerHTML = rowsHtml;
            }}

            if (modal) modal.style.display = 'flex';
        }}

        function submitToBackend(extracted, isExit = false) {{
            if (alreadySubmitted) return;
            alreadySubmitted = true;

            // Allow stopping audio on final test submission
            window.__bclAllowSubmissionPause = true;
            audioElements.forEach(a => {{ try {{ HTMLMediaElement.prototype.pause.call(a); }} catch(e) {{}} }});
            localStorage.removeItem(audioStorageKey);

            // Re-extract after checkAnswers was already called by bclTriggerSubmission
            const freshExtracted = extractAnswersAndScore();
            if (freshExtracted.score > extracted.score || Object.keys(freshExtracted.answers).length > Object.keys(extracted.answers).length) {{
                extracted = freshExtracted;
            }}

            const band = calculateBand(extracted.score);
            const payload = {{
                score: extracted.score,
                total: 40,
                band_score: band,
                answers: extracted.answers
            }};

            const formData = new FormData();
            formData.append('csrfmiddlewaretoken', csrfToken);
            formData.append('raw_score', extracted.score);
            formData.append('band_score', band);
            formData.append('module_type', 'listening');
            formData.append('attempt_id', String(attemptId));
            formData.append('answers_payload', JSON.stringify(payload));
            if (isExit) {{
                formData.append('exit_full_mock', 'true');
            }}

            fetch(submitUrl, {{
                method: 'POST',
                body: formData,
                headers: {{ 'X-Requested-With': 'XMLHttpRequest' }}
            }}).then(res => {{
                if (res.redirected) {{
                    window.location.replace(res.url);
                    return null;
                }}
                return res.json();
            }}).then(data => {{
                if (!data) return;
                if (!data || data.status !== 'ok') {{
                    throw new Error((data && data.error) || 'Listening submission failed.');
                }}
                console.log('Listening submission recorded to DB:', data);
                const confirmedNext = (data && data.next_url) ? data.next_url : (isExit ? (isFullMock ? endedUrl : '/dashboard/') : nextUrl);
                window.__bclConfirmedNextUrl = confirmedNext;

                if (isExit) {{
                    window.location.replace(confirmedNext);
                    return;
                }}

                const completedButton = document.getElementById('bclHeaderSubmitBtn');
                if (completedButton) {{
                    completedButton.innerHTML = '{next_btn_label}';
                    completedButton.onclick = function() {{ window.location.href = confirmedNext; }};
                }}
                const headerGroup = completedButton ? completedButton.parentElement : null;
                if (headerGroup && !document.getElementById('bclReopenResultsBtn')) {{
                    const reviewBtn = document.createElement('button');
                    reviewBtn.id = 'bclReopenResultsBtn';
                    reviewBtn.type = 'button';
                    reviewBtn.className = 'bcl-info-btn';
                    reviewBtn.style.marginRight = '8px';
                    reviewBtn.innerHTML = '📊 Results Summary';
                    reviewBtn.onclick = function() {{
                        const m = document.getElementById('bcl-listening-modal');
                        if (m) m.style.display = 'flex';
                    }};
                    headerGroup.insertBefore(reviewBtn, completedButton);
                }}
                hideAllLegacyModals();
                displayBclModal(extracted.score, band, extracted.answers);
                const proceedBtn = document.getElementById('bclModalNextBtn');
                if (proceedBtn) {{
                    proceedBtn.disabled = false;
                    proceedBtn.style.opacity = '1';
                    proceedBtn.innerHTML = '{next_btn_label}';
                    proceedBtn.onclick = function() {{ window.location.href = confirmedNext; }};
                }}
            }}).catch(err => {{
                console.error('Submission error:', err);
                alreadySubmitted = false;
                isBclSubmitting = false;
                alert('The Listening result could not be saved. Please check your connection and try again.');
                rearmHistoryTrap();
            }});
        }}

        hideAllLegacyModals();

        // History trap and confirmation handling matching Reading & Writing
        function rearmHistoryTrap() {{
            try {{
                window.history.pushState({{ examTrap: true, token: Date.now() }}, "", window.location.href);
            }} catch(e) {{
                console.warn("Could not push history trap state:", e);
            }}
        }}
        rearmHistoryTrap();

        function handleExitPrompt() {{
            if (alreadySubmitted) {{
                window.location.href = isFullMock ? endedUrl : '/dashboard/';
                return;
            }}
            const msg = isFullMock
                ? "Going back will exit your All-Module exam and submit your work so far. Are you sure you want to exit and submit?"
                : "Going back will submit your examination. Are you sure you want to exit and submit?";

            const confirmed = window.confirm(msg);
            if (confirmed) {{
                window.bclTriggerSubmission(true);
            }} else {{
                rearmHistoryTrap();
                setTimeout(rearmHistoryTrap, 50);
                setTimeout(rearmHistoryTrap, 200);
            }}
        }}
        window.handleExitPrompt = handleExitPrompt;

        let popstateHandling = false;
        try {{
            window.addEventListener('popstate', function() {{
                if (alreadySubmitted) return;
                rearmHistoryTrap();
                if (popstateHandling) return;
                popstateHandling = true;

                setTimeout(function() {{
                    try {{
                        handleExitPrompt();
                    }} finally {{
                        popstateHandling = false;
                        rearmHistoryTrap();
                    }}
                }}, 30);
            }});
        }} catch(e) {{
            console.warn("Could not register popstate listener:", e);
        }}

        document.addEventListener('click', function(e) {{
            // Dashboard / Back button in top header
            const backLink = e.target.closest('#bclHeaderBackBtn, .bcl-back-link[href*="dashboard"], a[href="/dashboard/"]');
            if (backLink) {{
                e.preventDefault();
                e.stopPropagation();
                handleExitPrompt();
                return;
            }}

            const btn = e.target.closest('#deliver-button, #checkButton, #check-btn, #btnCheckAnswers, .deliver-btn, .footer__deliverButton___3FM07, #modal-close-button');
            if (!btn) return;
            if (btn.id === 'modal-close-button') {{
                hideAllLegacyModals();
                return;
            }}
            const text = (btn.textContent || '').toLowerCase();
            if (text.includes('result') || text.includes('review') || text.includes('score')) {{
                const bclModal = document.getElementById('bcl-listening-modal');
                if (bclModal && alreadySubmitted) {{
                    e.preventDefault();
                    e.stopPropagation();
                    hideAllLegacyModals();
                    bclModal.style.display = 'flex';
                    return;
                }}
            }}
            // If in-page check or deliver button clicked while not yet submitted, trigger submission
            if (!alreadySubmitted && !isBclSubmitting) {{
                e.preventDefault();
                e.stopPropagation();
                window.bclTriggerSubmission(false);
            }}
        }}, true);
    }})();
    </script>
    """

    # Inject CSS in head
    if "</head>" in html_content:
        html_content = html_content.replace("</head>", bcl_design_css + "\n</head>")
    else:
        html_content = bcl_design_css + html_content

    # Inject Header at top of body
    if "<body" in html_content:
        idx = html_content.find("<body")
        closing_gt = html_content.find(">", idx)
        if closing_gt != -1:
            html_content = html_content[:closing_gt+1] + "\n" + bcl_header_html + "\n" + html_content[closing_gt+1:]
    else:
        html_content = bcl_header_html + html_content

    # Inject Modals & Bridge JS before </body>
    all_injections = bcl_modal_html + "\n" + bcl_instruction_modal_html + "\n" + bcl_violation_modal_html + "\n" + bcl_bridge_js
    if "</body>" in html_content:
        html_content = html_content.replace("</body>", all_injections + "\n</body>")
    else:
        html_content += "\n" + all_injections

    return HttpResponse(html_content, content_type="text/html; charset=utf-8")


@login_required
@require_GET
def exam_session(request, attempt_id):
    attempt = expire_attempt_if_needed(get_candidate_attempt(request, attempt_id))
    if attempt.status != CandidateAttempt.AttemptStatus.IN_PROGRESS:
        if attempt.full_mock_id:
            full_mock = FullMockAttempt.objects.filter(pk=attempt.full_mock_id, candidate=request.user).first()
            if full_mock and full_mock.status == FullMockAttempt.AttemptStatus.IN_PROGRESS:
                if attempt.module.module_type == ExamModule.ModuleType.LISTENING:
                    if full_mock.current_step == "listening":
                        full_mock.current_step = "reading"
                        full_mock.save(update_fields=["current_step"])
                    return redirect("bcl:full_mock_intermission", full_attempt_id=full_mock.pk)
                elif attempt.module.module_type == ExamModule.ModuleType.READING:
                    if full_mock.current_step in ("listening", "reading"):
                        full_mock.current_step = "writing"
                        full_mock.save(update_fields=["current_step"])
                    return redirect("bcl:full_mock_intermission", full_attempt_id=full_mock.pk)
                elif attempt.module.module_type == ExamModule.ModuleType.WRITING:
                    full_mock.status = attempt.status
                    full_mock.current_step = "completed"
                    full_mock.submitted_at = attempt.submitted_at or timezone.now()
                    full_mock.calculate_overall_score()
                    full_mock.save()
                    return redirect("bcl:full_mock_ended", full_attempt_id=full_mock.pk)
            return redirect("bcl:full_mock_ended", full_attempt_id=attempt.full_mock_id)
        return redirect("bcl:exam_ended", attempt_id=attempt.pk)
    # An older duplicate must not display an active exam interface.
    if is_superseded_active_attempt(attempt):
        return redirect("bcl:exam_rules", module_id=attempt.module_id)

    # Keep legacy HTML listening tests working until their content is migrated.
    # Any module with database sections is rendered by the normal exam interface.
    if (
        attempt.module.module_type == ExamModule.ModuleType.LISTENING
        and not attempt.module.sections.exists()
        and get_listening_filepath(attempt.module.mock_test.test_number, attempt.module)
    ):
        return render_listening_html(request, attempt)

    sections = list(attempt.module.sections.order_by("order", "pk").prefetch_related("questions__options"))
    for section in sections:
        section.has_valid_audio = is_audio_file(section.audio_file)
    if attempt.module.module_type == ExamModule.ModuleType.WRITING:
        writing_task_numbers = {
            question.pk: task_number
            for task_number, question in enumerate(
                get_writing_task_questions(attempt.module), start=1
            )
        }
        for section in sections:
            for question in section.questions.all():
                question.writing_task_number = writing_task_numbers.get(question.pk, question.order)

    global_counter = 1
    for section in sections:
        q_list, global_counter = annotate_question_groups(
            section.questions.order_by("order", "pk"),
            start_counter=global_counter
        )
        section.annotated_questions = q_list

    saved_answers = list(
        CandidateAnswer.objects.filter(attempt=attempt).values(
            "question_id", "answer_text", "is_flagged"
        )
    )
    module_audio_url = ""
    audio_file = getattr(attempt.module, "audio_file", None)
    if is_audio_file(audio_file):
        try:
            if audio_file.storage.exists(audio_file.name):
                module_audio_url = reverse("bcl:module_media", args=[attempt.pk, "audio"])
        except Exception:
            pass
    module_asset_url = ""
    module_asset_content_type = ""
    content_file = (
        getattr(attempt.module, "module_file", None)
        or getattr(attempt.module, "content_file", None)
    )
    if content_file and content_file.name:
        try:
            if content_file.storage.exists(content_file.name):
                module_asset_url = reverse("bcl:module_media", args=[attempt.pk, "content"])
                module_asset_content_type = (
                    mimetypes.guess_type(content_file.name)[0]
                    or "application/octet-stream"
                )
        except (OSError, ValueError):
            logger.warning("Unable to resolve module content file for attempt %s", attempt.pk)

    return render(request, "exam/session.html", {
        "attempt": attempt,
        "module": attempt.module,
        "mock_test": attempt.module.mock_test,
        "sections": sections,
        "remaining_seconds": get_remaining_seconds(attempt),
        "saved_answers": saved_answers,
        "module_audio_url": module_audio_url,
        "module_asset_url": module_asset_url,
        "module_asset_content_type": module_asset_content_type,
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
            if valid_keys and value not in valid_keys:
                if value.upper() in {k.upper() for k in valid_keys}:
                    value = value.upper()
                else:
                    return JsonResponse({"error": "Invalid option selection."}, status=400)
        if question.question_type == Question.QuestionType.MULTI_SELECT and value:
            valid_keys = {option.option_key for option in question.options.all()}
            selected_keys = [k.strip() for k in value.split(";;;") if k.strip()]
            if valid_keys and (not selected_keys or any(k not in valid_keys and k.upper() not in {vk.upper() for vk in valid_keys} for k in selected_keys)):
                return JsonResponse({"error": "Invalid multi-select selection."}, status=400)
        if question.question_type == Question.QuestionType.MAP_LABELLING and value:
            valid_keys = {option.option_key for option in question.options.all()}
            if valid_keys and value not in valid_keys:
                if value.upper() in {k.upper() for k in valid_keys}:
                    value = value.upper()
                else:
                    return JsonResponse({"error": "Invalid map label selection."}, status=400)
        if question.question_type == Question.QuestionType.TRUE_FALSE_NOT_GIVEN and value:
            val_upper = value.upper()
            if val_upper in {"TRUE", "FALSE", "NOT GIVEN"}:
                value = val_upper
            elif val_upper in {"T", "F", "NG"}:
                value = {"T": "TRUE", "F": "FALSE", "NG": "NOT GIVEN"}[val_upper]
            else:
                return JsonResponse({"error": "Invalid TFNG answer."}, status=400)
        if question.question_type == Question.QuestionType.YES_NO_NOT_GIVEN and value:
            val_upper = value.upper()
            if val_upper in {"YES", "NO", "NOT GIVEN"}:
                value = val_upper
            elif val_upper in {"Y", "N", "NG"}:
                value = {"Y": "YES", "N": "NO", "NG": "NOT GIVEN"}[val_upper]
            else:
                return JsonResponse({"error": "Invalid YNNG answer."}, status=400)
        if question.question_type in {
            Question.QuestionType.MATCHING,
            Question.QuestionType.MATCHING_INFORMATION,
        } and value:
            valid_keys = {option.option_key for option in question.options.all()}
            if valid_keys and value not in valid_keys:
                if value.upper() in {k.upper() for k in valid_keys}:
                    value = value.upper()
                else:
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
            up_fields = ["violation_count", "status", "submitted_at"]
            answers_p = payload.get("answers_payload")
            if answers_p:
                attempt.answers_payload = answers_p
                up_fields.append("answers_payload")
            if "raw_score" in payload:
                try:
                    raw_s = int(payload["raw_score"])
                    attempt.raw_score = raw_s
                    from .scoring import band_for_raw
                    from decimal import Decimal
                    attempt.band_score = Decimal(str(band_for_raw(attempt.module.module_type, raw_s)))
                    up_fields.extend(["raw_score", "band_score"])
                except Exception:
                    pass
            attempt.save(update_fields=up_fields)
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
            raw_score_val = request.POST.get("raw_score")
            if raw_score_val is not None:
                try:
                    raw_score_int = int(raw_score_val)
                    attempt.raw_score = raw_score_int
                    from .scoring import band_for_raw
                    from decimal import Decimal
                    attempt.band_score = Decimal(str(band_for_raw(attempt.module.module_type, raw_score_int)))
                except (ValueError, TypeError):
                    pass

            answers_payload_raw = request.POST.get("answers_payload") or request.POST.get("answers")
            if answers_payload_raw:
                try:
                    import json
                    if isinstance(answers_payload_raw, str):
                        attempt.answers_payload = json.loads(answers_payload_raw)
                    elif isinstance(answers_payload_raw, dict):
                        attempt.answers_payload = answers_payload_raw
                except Exception as exc:
                    logger.warning("Could not parse answers_payload for attempt %s: %s", attempt.pk, exc)

            if attempt.module.module_type == ExamModule.ModuleType.LISTENING:
                if isinstance(attempt.answers_payload, dict):
                    payload_score = attempt.answers_payload.get("score")
                    if payload_score is not None:
                        try:
                            attempt.raw_score = int(payload_score)
                            from .scoring import band_for_raw
                            from decimal import Decimal
                            attempt.band_score = Decimal(str(band_for_raw(attempt.module.module_type, attempt.raw_score)))
                        except (ValueError, TypeError):
                            pass

                if attempt.module.sections.exists() and isinstance(attempt.answers_payload, dict):
                    cand_answers = attempt.answers_payload.get("answers", {})
                    if cand_answers:
                        for q in Question.objects.filter(section__module=attempt.module):
                            ans_item = cand_answers.get(str(q.order)) or cand_answers.get(f"q{q.order}")
                            if ans_item and isinstance(ans_item, dict):
                                is_cor = bool(ans_item.get("is_correct", False))
                                CandidateAnswer.objects.update_or_create(
                                    attempt=attempt,
                                    question=q,
                                    defaults={
                                        "answer_text": ans_item.get("user_answer", ""),
                                        "is_correct": is_cor,
                                        "awarded_marks": 1 if is_cor else 0,
                                    }
                                )

            attempt.save(update_fields=["status", "submitted_at", "raw_score", "band_score", "answers_payload"])
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
                target_url = reverse("bcl:full_mock_result", args=[full_mock.pk]) if is_exit else reverse(
                    "bcl:full_mock_ended", args=[full_mock.pk]
                )
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return JsonResponse({
                        "status": "ok",
                        "raw_score": attempt.raw_score,
                        "band_score": str(attempt.band_score) if attempt.band_score else None,
                        "next_url": target_url,
                    })
                return redirect(target_url)
            elif attempt.module.module_type == ExamModule.ModuleType.LISTENING:
                full_mock.current_step = "reading"
                full_mock.listening_attempt = attempt
                full_mock.calculate_overall_score()
                full_mock.save(update_fields=["current_step", "listening_attempt", "overall_band_score"])
                messages.success(request, "Listening module completed. Next stage: Reading.")
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return JsonResponse({
                        "status": "ok",
                        "raw_score": attempt.raw_score,
                        "band_score": str(attempt.band_score) if attempt.band_score else None,
                        "next_url": reverse("bcl:mock_reading", args=[attempt.module.mock_test_id]),
                    })
                return redirect("bcl:mock_reading", mock_id=attempt.module.mock_test_id)
            elif attempt.module.module_type == ExamModule.ModuleType.READING:
                full_mock.current_step = "writing"
                full_mock.save(update_fields=["current_step"])
                messages.success(request, "Reading module completed. Next stage: Writing.")
                return redirect("bcl:exam_result", attempt_id=attempt.pk)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "status": "ok",
            "raw_score": attempt.raw_score,
            "band_score": str(attempt.band_score) if attempt.band_score else None,
            "next_url": reverse("bcl:dashboard"),
        })
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
    next_module_url = ""
    next_module_label = ""
    if attempt.full_mock_id and module_type == ExamModule.ModuleType.READING:
        next_module_url = reverse("bcl:mock_writing", args=[mock_test.pk])
        next_module_label = "Go to Writing Module"

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
        writing_task_numbers = {
            question.pk: task_number
            for task_number, question in enumerate(get_writing_task_questions(module), start=1)
        }
        answers = {
            a.question_id: a for a in CandidateAnswer.objects.filter(attempt=attempt)
        }
        sections_data = []
        for section in sections:
            questions_data = []
            for q in section.questions.order_by("order"):
                q.writing_task_number = writing_task_numbers.get(q.pk, q.order)
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
            "next_module_url": next_module_url,
            "next_module_label": next_module_label,
        })

    # Objective: Reading or Listening
    if attempt.status != CandidateAttempt.AttemptStatus.IN_PROGRESS and attempt.raw_score is None:
        finalize_attempt_score(attempt)
        attempt.refresh_from_db()
    sections = list(module.sections.order_by("order", "pk").prefetch_related("questions__options"))

    # Dedicated Listening Review: Render exact completion modal interface
    if module_type == ExamModule.ModuleType.LISTENING or (not sections and module_type == 'listening'):
        review_data = get_listening_review_data(attempt)
        if attempt.raw_score != review_data["raw_score"] or attempt.band_score is None:
            attempt.raw_score = review_data["raw_score"]
            from .scoring import band_for_raw
            from decimal import Decimal
            attempt.band_score = Decimal(str(band_for_raw(ExamModule.ModuleType.LISTENING, attempt.raw_score)))
            attempt.save(update_fields=["raw_score", "band_score"])

        return render(request, "exam/listening_result.html", {
            "attempt": attempt,
            "module": module,
            "mock_test": mock_test,
            "module_type": module_type,
            "review": review_data,
            "raw_score": review_data["raw_score"],
            "band_score": review_data["band_score"],
            "correct_count": review_data["correct_count"],
            "wrong_count": review_data["wrong_count"],
            "time_taken": review_data["time_taken"],
            "candidate_name": review_data["candidate_name"],
            "candidate_username": review_data["candidate_username"],
            "audio_url": review_data["audio_url"],
            "questions": review_data["questions"],
        })

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
        questions_list, next_counter = annotate_question_groups(
            section.questions.order_by("order", "pk"),
            start_counter=global_counter
        )
        global_counter = next_counter

        questions_data = []
        for q in questions_list:
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

            cand_norm = candidate_answer.strip().upper()
            corr_norm = (q.correct_answer or "").strip().upper()

            if q.question_type == Question.QuestionType.TRUE_FALSE_NOT_GIVEN:
                display_options = [
                    {"key": "TRUE", "text": "TRUE", "is_correct": corr_norm == "TRUE"},
                    {"key": "FALSE", "text": "FALSE", "is_correct": corr_norm == "FALSE"},
                    {"key": "NOT GIVEN", "text": "NOT GIVEN", "is_correct": corr_norm == "NOT GIVEN"},
                ]
            elif q.question_type == Question.QuestionType.YES_NO_NOT_GIVEN:
                display_options = [
                    {"key": "YES", "text": "YES", "is_correct": corr_norm == "YES"},
                    {"key": "NO", "text": "NO", "is_correct": corr_norm == "NO"},
                    {"key": "NOT GIVEN", "text": "NOT GIVEN", "is_correct": corr_norm == "NOT GIVEN"},
                ]
            elif q.options.exists():
                cand_keys = [x.strip().upper() for x in candidate_answer.split(";;;") if x.strip()]
                display_options = [
                    {
                        "key": opt.option_key,
                        "text": f"{opt.option_key}. {opt.option_text}",
                        "is_correct": opt.is_correct,
                        "is_selected": opt.option_key.strip().upper() in cand_keys,
                    }
                    for opt in q.options.order_by("order", "option_key")
                ]
            else:
                display_options = []

            if display_options and q.question_type in (Question.QuestionType.TRUE_FALSE_NOT_GIVEN, Question.QuestionType.YES_NO_NOT_GIVEN):
                for opt in display_options:
                    opt["is_selected"] = (opt["key"] == cand_norm)

            questions_data.append({
                "question": q,
                "global_num": q.global_num,
                "blank_count": getattr(q, "blank_count", 1),
                "group_header": getattr(q, "group_header", None),
                "candidate_answer": candidate_answer,
                "is_correct": is_correct,
                "is_blank": is_blank,
                "explanation": q.explanation,
                "display_options": display_options,
                "options": list(q.options.order_by("order", "option_key")),
            })

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
        "next_module_url": next_module_url,
        "next_module_label": next_module_label,
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

    listening_module = mock_test.modules.get(module_type=ExamModule.ModuleType.LISTENING, is_active=True)

    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        now = timezone.now()

        for active_full in FullMockAttempt.objects.select_for_update().filter(
            candidate=request.user,
            mock_test=mock_test,
            status=FullMockAttempt.AttemptStatus.IN_PROGRESS,
        ):
            for module_attempt in (
                active_full.listening_attempt,
                active_full.reading_attempt,
                active_full.writing_attempt,
            ):
                if module_attempt and module_attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
                    module_attempt.status = CandidateAttempt.AttemptStatus.AUTO_SUBMITTED
                    module_attempt.submitted_at = now
                    module_attempt.save(update_fields=["status", "submitted_at"])
            active_full.status = FullMockAttempt.AttemptStatus.SUBMITTED
            active_full.current_step = "completed"
            active_full.submitted_at = now
            active_full.calculate_overall_score()
            active_full.save(update_fields=["status", "current_step", "submitted_at", "overall_band_score"])

        active_full = FullMockAttempt.objects.create(
            candidate=request.user,
            mock_test=mock_test,
            status=FullMockAttempt.AttemptStatus.IN_PROGRESS,
            current_step="listening",
            started_at=now,
        )

        if not active_full.listening_attempt:
            listening_attempt = CandidateAttempt.objects.create(
                candidate=request.user,
                module=listening_module,
                full_mock=active_full,
                started_at=now,
                expires_at=now + timedelta(minutes=listening_module.duration_minutes),
                status=CandidateAttempt.AttemptStatus.IN_PROGRESS,
            )
            active_full.listening_attempt = listening_attempt
            active_full.save(update_fields=["listening_attempt"])
        else:
            listening_attempt = expire_attempt_if_needed(active_full.listening_attempt)
            if listening_attempt.status != CandidateAttempt.AttemptStatus.IN_PROGRESS:
                active_full.current_step = "reading"
                active_full.save(update_fields=["current_step"])
                return redirect("bcl:full_mock_intermission", full_attempt_id=active_full.pk)

    return redirect("bcl:exam_session", attempt_id=active_full.listening_attempt.pk)


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

    # Check if the attempt for the current step has already completed or expired
    if full_mock.current_step == "reading":
        if full_mock.reading_attempt:
            reading_att = expire_attempt_if_needed(full_mock.reading_attempt)
            if reading_att.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
                return redirect("bcl:exam_session", attempt_id=reading_att.pk)
            else:
                full_mock.current_step = "writing"
                full_mock.save(update_fields=["current_step"])
    elif full_mock.current_step == "writing":
        if full_mock.writing_attempt:
            writing_att = expire_attempt_if_needed(full_mock.writing_attempt)
            if writing_att.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
                return redirect("bcl:exam_session", attempt_id=writing_att.pk)
            else:
                full_mock.status = writing_att.status
                full_mock.current_step = "completed"
                full_mock.submitted_at = writing_att.submitted_at or timezone.now()
                full_mock.calculate_overall_score()
                full_mock.save()
                return redirect("bcl:full_mock_ended", full_attempt_id=full_mock.pk)

    step_info = {}
    if full_mock.current_step == "reading":
        step_info = {
            "completed_module_name": "Listening",
            "completed_attempt": full_mock.listening_attempt,
            "next_module_name": "Reading",
            "next_module_type": "reading",
            "next_duration": full_mock.mock_test.modules.get(
                module_type=ExamModule.ModuleType.READING, is_active=True
            ).duration_minutes,
            "stage_number": 2,
            "total_stages": 3,
            "tips": [
                "The Reading test has three passages and 40 questions.",
                "You can move between questions and review your answers before submitting.",
                "The Listening answers you submitted are now locked.",
            ],
        }
    elif full_mock.current_step == "writing":
        step_info = {
            "completed_module_name": "Reading",
            "completed_attempt": full_mock.reading_attempt,
            "next_module_name": "Writing",
            "next_module_type": "writing",
            "next_duration": full_mock.mock_test.modules.get(
                module_type=ExamModule.ModuleType.WRITING, is_active=True
            ).duration_minutes,
            "stage_number": 3,
            "total_stages": 3,
            "tips": [
                "Writing consists of Task 1 (recommended 20 mins, min 150 words) and Task 2 (recommended 40 mins, min 250 words).",
                "Your responses are autosaved regularly while you type.",
                "Writing will be submitted for manual review by certified examiners upon completion.",
            ],
        }
    else:
        if full_mock.listening_attempt:
            return redirect("bcl:exam_session", attempt_id=full_mock.listening_attempt.pk)
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
        if full_mock.current_step == "reading":
            reading_mod = full_mock.mock_test.modules.get(module_type=ExamModule.ModuleType.READING, is_active=True)
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
                full_mock.save(update_fields=["reading_attempt"])
            else:
                reading_att = expire_attempt_if_needed(full_mock.reading_attempt)
                if reading_att.status != CandidateAttempt.AttemptStatus.IN_PROGRESS:
                    full_mock.current_step = "writing"
                    full_mock.save(update_fields=["current_step"])
                    return redirect("bcl:full_mock_intermission", full_attempt_id=full_mock.pk)
            return redirect("bcl:exam_session", attempt_id=full_mock.reading_attempt.pk)

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
        if full_mock.current_step == "completed":
            full_mock.status = CandidateAttempt.AttemptStatus.SUBMITTED
            if not full_mock.submitted_at:
                full_mock.submitted_at = timezone.now()
            full_mock.calculate_overall_score()
            full_mock.save()
            return render(request, "exam/full_mock_ended.html", {
                "full_mock": full_mock,
                "mock_test": full_mock.mock_test,
            })

        if full_mock.current_step in {"listening", "reading", "writing"}:
            active_att = getattr(full_mock, f"{full_mock.current_step}_attempt", None)
            if not active_att:
                return redirect("bcl:full_mock_intermission", full_attempt_id=full_mock.pk)

            active_att = expire_attempt_if_needed(active_att)
            if active_att.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
                return redirect("bcl:exam_session", attempt_id=active_att.pk)

            # active_att has ended (auto_submitted or submitted)
            if full_mock.current_step == "listening":
                full_mock.current_step = "reading"
                full_mock.save(update_fields=["current_step"])
                return redirect("bcl:full_mock_intermission", full_attempt_id=full_mock.pk)
            elif full_mock.current_step == "reading":
                full_mock.current_step = "writing"
                full_mock.save(update_fields=["current_step"])
                return redirect("bcl:full_mock_intermission", full_attempt_id=full_mock.pk)
            elif full_mock.current_step == "writing":
                full_mock.status = active_att.status
                full_mock.current_step = "completed"
                full_mock.submitted_at = active_att.submitted_at or timezone.now()
                full_mock.calculate_overall_score()
                full_mock.save()

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

    if full_mock.reading_attempt or full_mock.listening_attempt or full_mock.writing_attempt:
        full_mock.calculate_overall_score()
        full_mock.save(update_fields=["overall_band_score"])

    writing_tasks = []
    if writing_att:
        ans_map = {a.question_id: a for a in CandidateAnswer.objects.filter(attempt=writing_att)}
        eval_map = {ev.task_number: ev for ev in writing_evaluations}
        for task_num, q in enumerate(get_writing_task_questions(writing_att.module), start=1):
            user_ans = ans_map.get(q.pk)
            ans_text = user_ans.answer_text if user_ans else ""
            words = len(ans_text.strip().split()) if ans_text.strip() else 0
            writing_tasks.append({
                "task_number": task_num,
                "section": q.section,
                "question": q,
                "answer_text": ans_text,
                "word_count": words,
                "evaluation": eval_map.get(task_num),
            })

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

    listening_review = None
    if full_mock.listening_attempt:
        listening_review = get_listening_review_data(full_mock.listening_attempt)

    return render(request, "exam/full_mock_result.html", {
        "listening_review": listening_review,
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
        "partial_result": not full_mock.writing_attempt or not full_mock.reading_attempt or not full_mock.listening_attempt,
    })


@login_required
def mock_listening_view(request, mock_id):
    """Architecture route: GET /mock/<id>/listening/ with independent practice support."""
    if not is_candidate(request.user):
        messages.error(request, "Candidates only.")
        return redirect("bcl:dashboard")

    mock_test = get_mock_test_object(mock_id)
    if not mock_test:
        raise Http404(f"Mock test {mock_id} not found.")
    listening_mod = get_object_or_404(
        ExamModule, mock_test=mock_test, module_type=ExamModule.ModuleType.LISTENING, is_active=True
    )

    is_individual = (
        request.GET.get("mode") in ("individual", "single", "practice")
        or request.GET.get("practice") == "1"
    )

    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        now = timezone.now()
        
        full_mock = None
        if not is_individual:
            # Check if candidate has an active full mock for this test currently at listening step
            full_mock = (
                FullMockAttempt.objects.select_for_update()
                .filter(
                    candidate=request.user,
                    mock_test=mock_test,
                    status=FullMockAttempt.AttemptStatus.IN_PROGRESS,
                    current_step="listening",
                )
                .order_by("-started_at")
                .first()
            )

        attempt = None
        if full_mock:
            # Taking listening as part of full mock
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
                expired_att = expire_attempt_if_needed(full_mock.listening_attempt)
                if expired_att.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
                    attempt = expired_att
                # If full mock listening is already completed, do NOT redirect to reading.
                # Treat as individual practice attempt so candidate can practice listening!

        if not attempt:
            # Individual Listening Practice: completely independent from full mock!
            active_attempt = (
                CandidateAttempt.objects.select_for_update()
                .filter(
                    candidate=request.user,
                    module=listening_mod,
                    status=CandidateAttempt.AttemptStatus.IN_PROGRESS,
                    full_mock__isnull=True,
                )
                .order_by("-started_at")
                .first()
            )
            if active_attempt:
                active_attempt = expire_attempt_if_needed(active_attempt)
                if active_attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
                    attempt = active_attempt

            if not attempt:
                # Fresh attempt: audio plays from start!
                attempt = CandidateAttempt.objects.create(
                    candidate=request.user,
                    module=listening_mod,
                    full_mock=None,
                    started_at=now,
                    expires_at=now + timedelta(minutes=listening_mod.duration_minutes),
                    status=CandidateAttempt.AttemptStatus.IN_PROGRESS,
                )

    if not get_listening_filepath(mock_test.test_number, listening_mod):
        return redirect("bcl:exam_session", attempt_id=attempt.pk)
    return render_listening_html(request, attempt)


@login_required
@require_POST
def mock_listening_submit(request, mock_id):
    """Architecture route: POST /mock/<id>/listening/submit/"""
    if not is_candidate(request.user):
        return JsonResponse({"error": "Candidates only."}, status=403)

    mock_test = get_mock_test_object(mock_id)
    if not mock_test:
        raise Http404(f"Mock test {mock_id} not found.")
    listening_mod = get_object_or_404(
        ExamModule, mock_test=mock_test, module_type=ExamModule.ModuleType.LISTENING, is_active=True
    )
    attempt = (
        CandidateAttempt.objects.filter(
            candidate=request.user, module=listening_mod, status=CandidateAttempt.AttemptStatus.IN_PROGRESS
        )
        .order_by("-started_at")
        .first()
    )
    if not attempt:
        completed_attempt = (
            CandidateAttempt.objects.filter(candidate=request.user, module=listening_mod)
            .order_by("-started_at")
            .first()
        )
        if completed_attempt:
            dest_url = reverse("bcl:mock_reading", args=[mock_id]) if completed_attempt.full_mock_id else reverse("bcl:dashboard")
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({
                    "status": "ok",
                    "raw_score": completed_attempt.raw_score,
                    "band_score": str(completed_attempt.band_score) if completed_attempt.band_score else None,
                    "next_url": dest_url,
                })
            return redirect(dest_url)
        return JsonResponse({"error": "No active listening attempt found."}, status=404)

    supplied_attempt_id = request.POST.get("attempt_id")
    if supplied_attempt_id and str(attempt.pk) != supplied_attempt_id:
        return JsonResponse({"error": "Listening session mismatch; no submission recorded."}, status=409)
    return submit_exam(request, attempt.pk)


@login_required
def mock_reading_view(request, mock_id):
    """Architecture route: GET /mock/<id>/reading/ with Server-Side Sequence Guard."""
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
            messages.warning(request, "Please start the mock exam from the Listening module.")
            return redirect("bcl:mock_listening", mock_id=mock_id)

        # Reading is never allowed to complete an unfinished Listening attempt.
        # Only an explicit Listening submission (or its expiry handler) may do so.
        listening_done = (
            full_mock.listening_attempt is not None
            and full_mock.listening_attempt.status != CandidateAttempt.AttemptStatus.IN_PROGRESS
        )
        step_already_advanced = full_mock.current_step in ("reading", "writing", "completed")
        if not listening_done and not step_already_advanced:
            messages.warning(request, "You must complete and submit the Listening module before starting Reading.")
            return redirect("bcl:mock_listening", mock_id=mock_id)

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
                return redirect("bcl:mock_writing", mock_id=mock_id)

    return redirect("bcl:exam_session", attempt_id=full_mock.reading_attempt.pk)


@login_required
@require_POST
def mock_reading_submit(request, mock_id):
    """Architecture route: POST /mock/<id>/reading/submit/"""
    if not is_candidate(request.user):
        return JsonResponse({"error": "Candidates only."}, status=403)

    mock_test = get_mock_test_object(mock_id)
    if not mock_test:
        raise Http404(f"Mock test {mock_id} not found.")
    reading_mod = get_object_or_404(
        ExamModule, mock_test=mock_test, module_type=ExamModule.ModuleType.READING, is_active=True
    )
    attempt = (
        CandidateAttempt.objects.filter(
            candidate=request.user, module=reading_mod, status=CandidateAttempt.AttemptStatus.IN_PROGRESS
        )
        .order_by("-started_at")
        .first()
    )
    if not attempt:
        return JsonResponse({"error": "No active reading attempt found."}, status=404)

    return submit_exam(request, attempt.pk)


@login_required
def mock_writing_view(request, mock_id):
    """Architecture route: GET /mock/<id>/writing/ with Server-Side Sequence Guard."""
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
            messages.warning(request, "Please start the mock exam from the Listening module.")
            return redirect("bcl:mock_listening", mock_id=mock_id)

        # Sequence Guard: Validate Listening and Reading are completed
        if full_mock.reading_attempt:
            expire_attempt_if_needed(full_mock.reading_attempt)

        if not full_mock.listening_attempt or full_mock.listening_attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
            messages.warning(request, "You must complete the Listening module first.")
            return redirect("bcl:mock_listening", mock_id=mock_id)

        if not full_mock.reading_attempt or full_mock.reading_attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
            messages.warning(request, "You must complete the Reading module before starting Writing.")
            return redirect("bcl:mock_reading", mock_id=mock_id)

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
                return redirect("bcl:mock_consolidated_result", mock_id=mock_id)

    return redirect("bcl:exam_session", attempt_id=full_mock.writing_attempt.pk)


@login_required
@require_POST
def mock_writing_submit(request, mock_id):
    """Architecture route: POST /mock/<id>/writing/submit/"""
    if not is_candidate(request.user):
        return JsonResponse({"error": "Candidates only."}, status=403)

    mock_test = get_mock_test_object(mock_id)
    if not mock_test:
        raise Http404(f"Mock test {mock_id} not found.")
    writing_mod = get_object_or_404(
        ExamModule, mock_test=mock_test, module_type=ExamModule.ModuleType.WRITING, is_active=True
    )
    attempt = (
        CandidateAttempt.objects.filter(
            candidate=request.user, module=writing_mod, status=CandidateAttempt.AttemptStatus.IN_PROGRESS
        )
        .order_by("-started_at")
        .first()
    )
    if not attempt:
        return JsonResponse({"error": "No active writing attempt found."}, status=404)

    return submit_exam(request, attempt.pk)


@login_required
@require_GET
def mock_consolidated_result(request, mock_id):
    """Architecture route: GET /mock/<id>/consolidated-result/"""
    if not is_candidate(request.user):
        return redirect("bcl:dashboard")

    mock_test = get_mock_test_object(mock_id)
    if not mock_test:
        raise Http404(f"Mock test {mock_id} not found.")
    full_mock = (
        FullMockAttempt.objects.filter(candidate=request.user, mock_test=mock_test)
        .order_by("-started_at")
        .first()
    )
    if full_mock:
        return redirect("bcl:full_mock_result", full_attempt_id=full_mock.pk)
    messages.info(request, "No mock attempt found for this test.")
    return redirect("bcl:dashboard")


@login_required
@require_POST
def start_mock_shortcut(request):
    """Architecture route: POST /start-mock/"""
    if not is_candidate(request.user):
        messages.error(request, "Candidates only.")
        return redirect("bcl:dashboard")
    mock_id = request.POST.get("mock_id") or request.POST.get("mock_test_id")
    if not mock_id:
        return JsonResponse({"error": "mock_id is required."}, status=400)
    mock_test = get_mock_test_object(mock_id)
    if not mock_test:
        raise Http404(f"Mock test {mock_id} not found.")

    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        now = timezone.now()
        for active_full in FullMockAttempt.objects.select_for_update().filter(
            candidate=request.user,
            mock_test=mock_test,
            status=FullMockAttempt.AttemptStatus.IN_PROGRESS,
        ):
            for module_attempt in (
                active_full.listening_attempt,
                active_full.reading_attempt,
                active_full.writing_attempt,
            ):
                if module_attempt and module_attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
                    module_attempt.status = CandidateAttempt.AttemptStatus.AUTO_SUBMITTED
                    module_attempt.submitted_at = now
                    module_attempt.save(update_fields=["status", "submitted_at"])
            active_full.status = FullMockAttempt.AttemptStatus.SUBMITTED
            active_full.current_step = "completed"
            active_full.submitted_at = now
            active_full.calculate_overall_score()
            active_full.save(update_fields=["status", "current_step", "submitted_at", "overall_band_score"])

        full_mock = FullMockAttempt.objects.create(
            candidate=request.user,
            mock_test=mock_test,
            status=FullMockAttempt.AttemptStatus.IN_PROGRESS,
            current_step="listening",
            started_at=now,
        )
    return redirect("bcl:mock_listening", mock_id=mock_id)
