import os
from datetime import timedelta
import json
import logging
import uuid

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

    if module.module_type == ExamModule.ModuleType.LISTENING:
        return redirect("bcl:mock_listening", mock_id=module.mock_test_id)
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



LISTENING_BRIDGE_TEMPLATE = r"""
<!-- BCL IELTS Architecture: Listening Client-Side Bridge -->
<script>
(function() {
    const mockId = __MOCK_ID__;
    const submitUrl = "__SUBMIT_URL__";
    const nextUrl = "__NEXT_URL__";
    const csrfToken = "__CSRF_TOKEN__";
    let alreadySubmitted = false;

    function getCalculatedScore() {
        const scoreSum = document.getElementById('score-summary');
        if (scoreSum && scoreSum.textContent) {
            const m = scoreSum.textContent.match(/(\d+)\s*(?:out of|\/)\s*40/i);
            if (m) return parseInt(m[1], 10);
        }
        const resTotal = document.getElementById('res-total-score');
        if (resTotal && resTotal.textContent) {
            const m = resTotal.textContent.match(/(\d+)/);
            if (m) return parseInt(m[1], 10);
        }
        const delBtn = document.getElementById('deliver-button');
        if (delBtn && delBtn.textContent) {
            const m = delBtn.textContent.match(/(\d+)\s*\/\s*40/i);
            if (m) return parseInt(m[1], 10);
        }
        if (typeof window.totalCorrect !== 'undefined') return window.totalCorrect;
        if (typeof window.score !== 'undefined') return window.score;
        return 0;
    }

    function submitToBackend(score) {
        if (alreadySubmitted) return;
        alreadySubmitted = true;

        const formData = new FormData();
        formData.append('csrfmiddlewaretoken', csrfToken);
        formData.append('raw_score', score);
        formData.append('module_type', 'listening');

        document.querySelectorAll('input[type="text"], input[type="radio"]:checked, input[type="checkbox"]:checked, textarea, select').forEach(function(el) {
            if (el.name) {
                formData.append(el.name, el.value);
            }
        });

        fetch(submitUrl, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        }).then(function(res) {
            return res.json();
        }).then(function(data) {
            console.log('Listening submission recorded:', data);
        }).catch(function(err) {
            console.error('Submission error:', err);
        });
    }

    function attachProceedUI() {
        if (document.getElementById('bcl-proceed-container')) return;

        const container = document.createElement('div');
        container.id = 'bcl-proceed-container';
        container.style.cssText = "margin-top: 24px; padding: 20px; text-align: center; background: #f8fafc; border-top: 2px solid #e2e8f0; border-radius: 0 0 12px 12px;";

        const btn = document.createElement('button');
        btn.id = 'bcl-proceed-btn';
        btn.style.cssText = "background: #2563eb; color: #ffffff; font-size: 16px; font-weight: bold; padding: 12px 32px; border: none; border-radius: 8px; cursor: pointer; box-shadow: 0 4px 6px -1px rgba(37,99,235,0.3); transition: all 0.2s;";
        btn.innerHTML = "Proceed to Reading Module &rarr;";

        btn.onmouseover = function() { btn.style.background = "#1d4ed8"; };
        btn.onmouseout = function() { btn.style.background = "#2563eb"; };
        btn.onclick = function() {
            window.location.href = nextUrl;
        };

        container.appendChild(btn);

        const modalBody = document.querySelector('.modal-body')
            || document.getElementById('results-modal')
            || document.getElementById('result-modal')
            || document.body;

        modalBody.appendChild(container);
    }

    const origCheckAnswers = window.checkAnswers;
    window.checkAnswers = function() {
        if (origCheckAnswers) {
            try { origCheckAnswers.apply(this, arguments); } catch(e) { console.error(e); }
        }
        setTimeout(function() {
            const s = getCalculatedScore();
            submitToBackend(s);
            attachProceedUI();
        }, 350);
    };
})();
</script>
"""



def get_mock_test_object(mock_id):
    """Resolve IELTSMockTest by pk or test_number."""
    return (
        IELTSMockTest.objects.filter(pk=mock_id, is_published=True).first()
        or IELTSMockTest.objects.filter(test_number=mock_id, is_published=True).first()
    )


def get_listening_filepath(mock_num):
    """Resolve file path to listening-mock-<N>.html across supported directories."""
    candidates = [
        os.path.join(r"D:\BCL-Bhuiyan\listening", f"listening-mock-{mock_num}.html"),
        os.path.join(r"D:\BCL-Bhuiyan\bcl_bhuiyan\listening", f"listening-mock-{mock_num}.html"),
        os.path.join(settings.BASE_DIR, "listening", f"listening-mock-{mock_num}.html"),
        os.path.join(settings.BASE_DIR.parent, "listening", f"listening-mock-{mock_num}.html"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    for p in [
        os.path.join(r"D:\BCL-Bhuiyan\listening", "listening-mock-1.html"),
        os.path.join(r"D:\BCL-Bhuiyan\bcl_bhuiyan\listening", "listening-mock-1.html"),
    ]:
        if os.path.exists(p):
            return p
    return None

def render_listening_html(request, attempt):
    r"""
    Render client-side raw HTML listening module from D:\BCL-Bhuiyan\listening\
    Styled to seamlessly match the website design system (Geist font, modern cards, indigo accents),
    with full student info, score, and answer payload persisted to database on submit, plus modern completion modal.
    Authoritative 35-minute timer ensures 35:00 countdown both in dashboard and exam session.
    Audio engine enforces continuous IELTS audio: audio can be started but CANNOT be paused even on page reload.
    Includes initial exam instruction modal upon entry and full exam integrity tab-switching monitoring with auto-submit.
    """
    import os
    import json
    from django.middleware.csrf import get_token
    from .scoring import band_for_raw

    mock_test = attempt.module.mock_test
    mock_num = mock_test.test_number
    filepath = get_listening_filepath(mock_num)
    if not filepath or not os.path.exists(filepath):
        logger.error("Could not find listening file for Mock %s", mock_num)
        return HttpResponse(f"Error: listening-mock-{mock_num}.html not found.", status=404)

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            html_content = f.read()
    except Exception as exc:
        logger.error("Error reading listening file %s: %s", filepath, exc)
        return HttpResponse(f"Error loading listening module for Mock Test {mock_num}.", status=500)

    # Enforce authoritative 35-minute module duration
    now = timezone.now()
    if attempt.module.duration_minutes != 35:
        attempt.module.duration_minutes = 35
        attempt.module.save(update_fields=["duration_minutes"])

    max_seconds = 35 * 60  # 2100 seconds
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

        /* Suppress third-party links, disparate unstyled headers and raw modals */
        .header:not(#bcl-exam-header),
        header:not(#bcl-exam-header),
        .fixed-header:not(#bcl-exam-header),
        .app-header:not(#bcl-exam-header),
        .telegram-link,
        .telegram-pin,
        #resultsModal {
            display: none !important;
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

        /* Modern Audio Bar & Equalizer */
        .audio-bar, .listening-player-bar, .audio-player-container {
            height: 64px !important;
            position: fixed !important;
            top: 60px !important;
            left: 0 !important;
            right: 0 !important;
            z-index: 99 !important;
            background: linear-gradient(to right, rgba(238, 242, 255, 0.98), rgba(255, 255, 255, 0.98)) !important;
            border-bottom: 1px solid #c7d2fe !important;
            display: flex !important;
            align-items: center !important;
            padding: 0 20px !important;
            box-shadow: 0 1px 3px rgba(79, 70, 229, 0.04) !important;
        }

        .audio-shell {
            background: #ffffff !important;
            border: 1px solid #c7d2fe !important;
            border-radius: 12px !important;
            box-shadow: 0 1px 3px rgba(79, 70, 229, 0.06) !important;
            width: 100% !important;
            max-width: 1260px !important;
            margin: 0 auto !important;
            height: 44px !important;
            display: flex !important;
            align-items: center !important;
            padding: 0 12px !important;
            gap: 12px !important;
        }

        .audio-play {
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%) !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 9999px !important;
            padding: 6px 16px !important;
            font-size: 13px !important;
            font-weight: 700 !important;
            display: inline-flex !important;
            align-items: center !important;
            gap: 6px !important;
            box-shadow: 0 2px 6px rgba(79, 70, 229, 0.3) !important;
            cursor: pointer !important;
            transition: all 0.15s ease !important;
        }
        .audio-play.playing {
            background: linear-gradient(135deg, #059669 0%, #10b981 100%) !important;
            box-shadow: 0 2px 6px rgba(16, 185, 129, 0.3) !important;
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

        #seekSlider {
            accent-color: #4f46e5 !important;
        }
        #volumeSlider {
            accent-color: #4f46e5 !important;
        }
        .time-text {
            font-family: var(--font-mono) !important;
            font-size: 13px !important;
            font-weight: 600 !important;
            color: #475569 !important;
        }

        /* Workspace & Question Containers */
        .main-area, .main-container {
            top: 124px !important;
            bottom: 72px !important;
            background: var(--bcl-bg) !important;
            font-family: var(--font-sans) !important;
        }

        .questions-panel {
            background: var(--bcl-bg) !important;
            padding: 16px 20px 100px 20px !important;
        }

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
        .section-banner p {
            font-size: 14.5px !important;
            font-weight: 600 !important;
            color: #1e1b4b !important;
            margin: 0 !important;
        }
        .section-banner p + p {
            font-size: 13px !important;
            font-weight: 400 !important;
            color: #475569 !important;
            margin-top: 2px !important;
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

        /* Options */
        .mc-option, .pick-option, .question-option, .option-item, label:has(input[type="radio"]), label:has(input[type="checkbox"]) {
            font-family: var(--font-sans) !important;
            font-size: 14px !important;
            border-radius: 8px !important;
            border: 1px solid #e2e8f0 !important;
            background: #ffffff !important;
            padding: 9px 14px !important;
            margin-bottom: 7px !important;
            cursor: pointer !important;
            transition: all 0.15s ease !important;
        }
        .mc-option:hover, .pick-option:hover, .question-option:hover, .option-item:hover, label:has(input[type="radio"]):hover, label:has(input[type="checkbox"]):hover {
            background: #f8fafc !important;
            border-color: #c7d2fe !important;
        }
        .mc-option:has(input:checked), .pick-option:has(input:checked) {
            background: #eef2ff !important;
            border-color: #818cf8 !important;
            color: #3730a3 !important;
            font-weight: 600 !important;
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

        .section-tab, .footer__questionNo___3WNct, .part-btn, .nav-tab, .tab-btn {
            font-family: var(--font-sans) !important;
            font-size: 13.5px !important;
            font-weight: 600 !important;
            padding: 8px 16px !important;
            border-radius: 8px !important;
            border: 1px solid #e2e8f0 !important;
            background: #ffffff !important;
            color: #475569 !important;
            cursor: pointer !important;
            transition: all 0.15s ease !important;
        }
        .section-tab.active, .footer__questionWrapper___1tZ46.selected .footer__questionNo___3WNct, .part-btn.active, .nav-tab.active, .tab-btn.active {
            background: #eef2ff !important;
            color: #4f46e5 !important;
            border-color: #c7d2fe !important;
            font-weight: 700 !important;
            box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2) !important;
        }

        .subQuestion {
            font-family: var(--font-mono) !important;
            font-size: 13px !important;
            font-weight: 600 !important;
            border-radius: 6px !important;
            border: 1px solid #cbd5e1 !important;
            background: #ffffff !important;
            color: #334155 !important;
            transition: all 0.15s ease !important;
        }
        .subQuestion.active {
            background: #4f46e5 !important;
            border-color: #4f46e5 !important;
            color: #ffffff !important;
            box-shadow: 0 2px 6px rgba(79, 70, 229, 0.35) !important;
        }
        .subQuestion.answered {
            background: #e0e7ff !important;
            border-color: #a5b4fc !important;
            color: #3730a3 !important;
        }

        .check-btn {
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%) !important;
            color: #ffffff !important;
            font-family: var(--font-sans) !important;
            font-size: 13.5px !important;
            font-weight: 700 !important;
            border-radius: 8px !important;
            border: none !important;
            padding: 9px 20px !important;
            box-shadow: 0 3px 10px rgba(79, 70, 229, 0.3) !important;
            cursor: pointer !important;
            transition: all 0.15s ease !important;
        }
        .check-btn:hover {
            background: linear-gradient(135deg, #4338ca 0%, #6d28d9 100%) !important;
            transform: translateY(-1px);
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
            <a href="/dashboard/" class="bcl-back-link" title="Exit to Candidate Dashboard">&larr; Dashboard</a>
            <div class="bcl-brand-badge">🎧</div>
            <div class="bcl-title-box">
                <span class="bcl-main-title">Test {mock_num}: {mock_test.title}</span>
                <span class="bcl-sub-meta">Module Attempt #{attempt.pk} &bull; {stage_pill}</span>
            </div>
        </div>

        <div class="bcl-header-group">
            <div class="bcl-timer-pill" title="Exam Timer">
                <span>⏱️</span>
                <span id="bclHeaderTimer">35:00</span>
            </div>
            <div class="bcl-user-badge">
                Candidate: <strong>{candidate_name}</strong>
            </div>
            <button type="button" class="bcl-info-btn" onclick="bclShowInstructions()" title="View Exam Instructions">
                ℹ️ Instructions
            </button>
        </div>

        <div class="bcl-header-group">
            <button type="button" class="bcl-submit-btn" id="bclHeaderSubmitBtn" onclick="bclTriggerSubmission()">
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
                <button type="button" class="bcl-submit-btn" onclick="window.location.href='{next_url}'">
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
                    <p class="bcl-instruction-sub">Test {mock_num}: {mock_test.title} &bull; 40 Questions &bull; 35 Minutes</p>
                </div>
            </div>

            <div class="bcl-instruction-body">
                <!-- Audio Notice Box -->
                <div class="bcl-notice-card audio-notice">
                    <div class="bcl-notice-icon">🔊</div>
                    <div class="bcl-notice-content">
                        <strong>Continuous Audio Recording (Plays ONCE only)</strong>
                        <div>The recording will play continuously from start to finish. Once started, <strong>it cannot be paused, rewound, or stopped</strong>. Please adjust your audio volume to a comfortable level now before starting.</div>
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
                        <span><strong>35-Minute Server Timer:</strong> The countdown starts immediately. Refreshing the browser does not pause your exam timer or audio.</span>
                    </div>
                    <div class="bcl-rule-item">
                        <span class="bcl-check-bullet">&check;</span>
                        <span><strong>Submission:</strong> When finished, click <em>Submit Listening &check;</em> to record your score and review your answers.</span>
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

    # Client-Side Bridge JavaScript with Authoritative 35:00 Timer, Continuous Audio Engine, and Tab-Switch Detection
    bcl_bridge_js = f"""
    <script>
    (function() {{
        const mockId = {mock_id};
        const submitUrl = "{submit_url}";
        const nextUrl = "{next_url}";
        const violationUrl = "{violation_url}";
        const endedUrl = "{ended_url}";
        const csrfToken = "{csrf_token}";
        let alreadySubmitted = false;

        // Authoritative 35-Minute Timer (strictly starts at 35:00 or remaining seconds)
        let timeRemaining = {remaining_seconds};
        if (!timeRemaining || timeRemaining <= 0 || isNaN(timeRemaining)) {{
            timeRemaining = 35 * 60;
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
                    if (timeRemaining <= 300) {{
                        el.style.color = '#dc2626';
                    }}
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
                alert("Time is up (35 minutes)! Your listening answers are being submitted.");
                bclTriggerSubmission();
            }}
        }}, 1000);

        window.toggleTimer = function() {{}};
        window.startTimer = function() {{}};

        // =========================================================================
        // INSTRUCTION MODAL CONTROLS
        // =========================================================================
        window.bclDismissInstructions = function() {{
            const m = document.getElementById('bcl-instruction-modal');
            if (m) m.style.display = 'none';
        }};

        window.bclShowInstructions = function() {{
            const m = document.getElementById('bcl-instruction-modal');
            if (m) m.style.display = 'flex';
        }};

        // =========================================================================
        // BCL IELTS CONTINUOUS AUDIO ENGINE: Start Once, Never Pause, Persist on Reload
        // =========================================================================
        const audioStorageKey = 'bcl_listening_audio_' + mockId;
        window.__bclAllowSubmissionPause = false;
        let audioEl = null;

        function getAudioElement() {{
            return document.getElementById('mainAudio') 
                || document.getElementById('global-audio-player') 
                || document.getElementById('audio1') 
                || document.querySelector('audio');
        }}

        function updatePlayButtonsUI(isPlaying) {{
            const playBtns = document.querySelectorAll('#audioPlay, #play-pause-btn, .audio-play, #btnPlayAudio');
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

        function lockAudioContinuous(audio) {{
            if (!audio || audio.__bclLocked) return;
            audio.__bclLocked = true;

            const origPause = HTMLMediaElement.prototype.pause;
            window.__bclOrigAudioPause = origPause;

            // Strict prevention: audio cannot be paused once started
            audio.pause = function() {{
                if (window.__bclAllowSubmissionPause) {{
                    origPause.call(audio);
                }} else {{
                    console.warn("BCL IELTS Architecture: Listening audio cannot be paused during examination.");
                }}
            }};

            // Record start epoch and persist continuous playback
            audio.addEventListener('play', function() {{
                let state = null;
                try {{
                    state = JSON.parse(localStorage.getItem(audioStorageKey) || '{{}}');
                }} catch(e) {{}}
                if (!state || !state.is_started) {{
                    state = {{
                        is_started: true,
                        start_epoch: Date.now() - (audio.currentTime * 1000)
                    }};
                    localStorage.setItem(audioStorageKey, JSON.stringify(state));
                }}
                updatePlayButtonsUI(true);
            }});

            // Continuously update position into localStorage
            audio.addEventListener('timeupdate', function() {{
                try {{
                    let state = JSON.parse(localStorage.getItem(audioStorageKey) || '{{}}');
                    state.is_started = true;
                    state.last_pos = audio.currentTime;
                    if (!state.start_epoch) {{
                        state.start_epoch = Date.now() - (audio.currentTime * 1000);
                    }}
                    localStorage.setItem(audioStorageKey, JSON.stringify(state));
                }} catch(e) {{}}
            }});

            // Disable skip buttons and lock seek slider for IELTS test integrity
            document.querySelectorAll('#back10, #forward10, .skip-btn').forEach(function(btn) {{
                btn.style.display = 'none';
            }});
            const seekSlider = document.getElementById('seekSlider');
            if (seekSlider) {{
                seekSlider.style.pointerEvents = 'none';
                seekSlider.style.opacity = '0.85';
            }}
        }}

        function showAutoplayResumePill(targetPos) {{
            if (document.getElementById('bclAudioResumeBanner')) return;
            const banner = document.createElement('div');
            banner.id = 'bclAudioResumeBanner';
            banner.style.cssText = 'position:fixed; top:66px; left:50%; transform:translateX(-50%); z-index:100000; background:linear-gradient(135deg, #4f46e5, #7c3aed); color:#fff; padding:8px 22px; border-radius:9999px; font-weight:700; font-size:13.5px; box-shadow:0 8px 24px rgba(79,70,229,0.35); cursor:pointer; display:flex; align-items:center; gap:8px; animation:bclAudioPulse 1.5s infinite alternate;';
            banner.innerHTML = '<span>🎧 Listening Audio in Progress &bull; Click anywhere to resume audio</span>';

            const resumeAction = function() {{
                if (audioEl) {{
                    if (targetPos && !isNaN(targetPos)) audioEl.currentTime = targetPos;
                    audioEl.play();
                }}
                if (banner && banner.parentNode) banner.parentNode.removeChild(banner);
                document.removeEventListener('click', resumeAction);
            }};

            banner.addEventListener('click', resumeAction);
            document.addEventListener('click', resumeAction, {{ once: true }});
            document.body.appendChild(banner);
        }}

        function initAudioEngine() {{
            audioEl = getAudioElement();
            if (!audioEl) {{
                setTimeout(initAudioEngine, 250);
                return;
            }}

            lockAudioContinuous(audioEl);

            // Check if audio was already playing before reload
            let state = null;
            try {{
                state = JSON.parse(localStorage.getItem(audioStorageKey) || '{{}}');
            }} catch(e) {{}}

            if (state && state.is_started) {{
                const elapsed = Math.max(0, (Date.now() - (state.start_epoch || Date.now())) / 1000);
                const targetPos = (elapsed > 0 && elapsed < (audioEl.duration || 3600)) ? elapsed : (state.last_pos || 0);

                const tryResumeAudio = function() {{
                    try {{
                        if (targetPos && !isNaN(targetPos)) {{
                            audioEl.currentTime = targetPos;
                        }}
                        const p = audioEl.play();
                        if (p && p.catch) {{
                            p.catch(function() {{
                                showAutoplayResumePill(targetPos);
                            }});
                        }}
                    }} catch(e) {{
                        showAutoplayResumePill(targetPos);
                    }}
                }};

                if (audioEl.readyState >= 1) {{
                    tryResumeAudio();
                }} else {{
                    audioEl.addEventListener('loadedmetadata', tryResumeAudio, {{ once: true }});
                    audioEl.addEventListener('canplay', tryResumeAudio, {{ once: true }});
                    setTimeout(tryResumeAudio, 600);
                }}
            }} else {{
                // Fresh test start: Display initial instructions modal
                bclShowInstructions();
            }}

            // Intercept play buttons so clicking again cannot pause audio
            const playBtns = document.querySelectorAll('#audioPlay, #play-pause-btn, .audio-play, #btnPlayAudio');
            playBtns.forEach(function(btn) {{
                btn.addEventListener('click', function(e) {{
                    let s = null;
                    try {{ s = JSON.parse(localStorage.getItem(audioStorageKey) || '{{}}'); }} catch(err) {{}}
                    if (s && s.is_started && !audioEl.paused) {{
                        e.preventDefault();
                        e.stopPropagation();
                        return false;
                    }}
                    audioEl.play();
                }}, true);
            }});

            if (typeof window.toggleAudio === 'function') {{
                window.toggleAudio = function() {{
                    if (audioEl && audioEl.paused) {{
                        audioEl.play();
                    }}
                }};
            }}
        }}

        initAudioEngine();

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
            try {{
                extractedAnswers = extractAnswersAndScore();
            }} catch(e) {{}}

            const reqPayload = {{
                reason: reason
            }};
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

                const data = await response.json().catch(function() {{ return {{}}; }});

                if (response.status === 409 || data.status === 'auto_submitted' || data.auto_submitted) {{
                    finishing = true;
                    alreadySubmitted = true;
                    window.__bclAllowSubmissionPause = true;
                    try {{
                        const audio = getAudioElement();
                        if (audio && window.__bclOrigAudioPause) {{
                            window.__bclOrigAudioPause.call(audio);
                        }}
                        localStorage.removeItem(audioStorageKey);
                    }} catch(e) {{}}

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

        window.bclDismissViolation = function() {{
            const vModal = document.getElementById('bcl-violation-modal');
            if (vModal) vModal.style.display = 'none';
            warningOpen = false;
            lastViolationAt = 0;
        }};

        document.addEventListener('visibilitychange', function() {{
            if (document.hidden) {{
                reportViolation('tab_hidden');
            }} else {{
                if (warningOpen) {{
                    const ackBtn = document.getElementById('bclAcknowledgeViolation');
                    if (ackBtn) ackBtn.focus();
                }}
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
        // SUBMISSION & REVIEW MODAL
        // =========================================================================
        window.bclCloseModal = function() {{
            const m = document.getElementById('bcl-listening-modal');
            if (m) m.style.display = 'none';
        }};

        window.bclTriggerSubmission = function() {{
            if (typeof window.checkAnswers === 'function') {{
                window.checkAnswers();
            }} else {{
                const dBtn = document.getElementById('checkButton') 
                    || document.getElementById('deliver-button') 
                    || document.getElementById('btnCheckAnswers')
                    || document.querySelector('.check-btn')
                    || document.querySelector('.deliver-btn');
                if (dBtn) dBtn.click();
            }}
        }};

        function extractAnswersAndScore() {{
            let score = 0;
            let answers = {{}};

            // Extract score
            const scoreSum = document.getElementById('resultsSummary')
                || document.getElementById('score-summary')
                || document.getElementById('scoreSummary');
            if (scoreSum && scoreSum.textContent) {{
                const m = scoreSum.textContent.match(/(\d+)\s*(?:out of|\/)\s*40/i);
                if (m) score = parseInt(m[1], 10);
            }}
            const resScore = document.getElementById('resScore') || document.getElementById('res-total-score');
            if (!score && resScore && resScore.textContent) {{
                const m = resScore.textContent.match(/(\d+)/);
                if (m) score = parseInt(m[1], 10);
            }}
            const delBtn = document.getElementById('checkButton') || document.getElementById('deliver-button');
            if (!score && delBtn && delBtn.textContent) {{
                const m = delBtn.textContent.match(/(\d+)\s*\/\s*40/i);
                if (m) score = parseInt(m[1], 10);
            }}
            if (!score) {{
                if (typeof window.totalCorrect !== 'undefined') score = window.totalCorrect;
                else if (typeof window.score !== 'undefined') score = window.score;
            }}

            // Extract question-by-question breakdown
            // Pattern A: #resultsTable .result-row (Vol 3 test 9, Vol 3 test 10, modern IELTS format)
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
                        answers[qNum] = {{
                            "user_answer": uAns,
                            "correct_answer": cAns,
                            "is_correct": isCor
                        }};
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
                            const isCor = cols[3].classList.contains('result-correct') 
                                || cols[3].textContent.includes('✓') 
                                || cols[3].textContent.includes('Correct');
                            answers[qNum] = {{
                                "user_answer": uAns,
                                "correct_answer": cAns,
                                "is_correct": isCor
                            }};
                        }}
                    }}
                }}
            }}

            // Pattern C: #resultsTableBody (Mock 22-30 format)
            if (Object.keys(answers).length === 0) {{
                const resRows = document.querySelectorAll('#resultsTableBody .result-row, #resultsTableBody tr');
                if (resRows.length > 0) {{
                    resRows.forEach(function(row) {{
                        const qEl = row.querySelector('.res-q-num') || row.children[0];
                        const uEl = row.querySelector('.res-user-ans') || row.children[1];
                        const cEl = row.querySelector('.res-correct-ans') || row.children[2];
                        const sEl = row.querySelector('.res-status') || row.children[3];
                        if (qEl && uEl && cEl) {{
                            const qNum = qEl.textContent.trim();
                            const uAns = uEl.textContent.trim();
                            const cAns = cEl.textContent.trim();
                            const isCor = row.classList.contains('res-correct') || (sEl && sEl.textContent.includes('✓'));
                            answers[qNum] = {{
                                "user_answer": uAns,
                                "correct_answer": cAns,
                                "is_correct": isCor
                            }};
                        }}
                    }});
                }}
            }}

            // Fallback: Scan DOM inputs
            if (Object.keys(answers).length === 0) {{
                for (let i = 1; i <= 40; i++) {{
                    const input = document.getElementById('q' + i) 
                        || document.querySelector('input[name="q' + i + '"]:checked') 
                        || document.querySelector('input[name="q' + i + '"]');
                    if (input) {{
                        answers[String(i)] = {{
                            "user_answer": input.value || "",
                            "correct_answer": "",
                            "is_correct": input.classList.contains('correct')
                        }};
                    }}
                }}
            }}

            return {{
                score: score,
                answers: answers
            }};
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
            if (score >= 10) return "4.0";
            if (score >= 8) return "3.5";
            if (score >= 6) return "3.0";
            if (score >= 4) return "2.5";
            return "2.0";
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
                const keys = Object.keys(answers).sort(function(a, b) {{
                    const na = parseInt(a, 10) || 0;
                    const nb = parseInt(b, 10) || 0;
                    return na - nb;
                }});

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

        function submitToBackend(extracted) {{
            if (alreadySubmitted) return;
            alreadySubmitted = true;

            // Allow stopping audio on final test submission
            window.__bclAllowSubmissionPause = true;
            try {{
                const audio = getAudioElement();
                if (audio && window.__bclOrigAudioPause) {{
                    window.__bclOrigAudioPause.call(audio);
                }}
                localStorage.removeItem(audioStorageKey);
            }} catch(e) {{}}

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
            formData.append('answers_payload', JSON.stringify(payload));

            fetch(submitUrl, {{
                method: 'POST',
                body: formData,
                headers: {{
                    'X-Requested-With': 'XMLHttpRequest'
                }}
            }}).then(function(res) {{
                return res.json();
            }}).then(function(data) {{
                console.log('Listening submission recorded to DB successfully:', data);
            }}).catch(function(err) {{
                console.error('Submission error:', err);
            }});

            displayBclModal(extracted.score, band, extracted.answers);
        }}

        const origCheckAnswers = window.checkAnswers;
        window.checkAnswers = function() {{
            if (origCheckAnswers) {{
                try {{ origCheckAnswers.apply(this, arguments); }} catch(e) {{ console.error(e); }}
            }}
            setTimeout(function() {{
                const extracted = extractAnswersAndScore();
                submitToBackend(extracted);
            }}, 350);
        }};
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
            return redirect("bcl:full_mock_ended", full_attempt_id=attempt.full_mock_id)
        return redirect("bcl:exam_ended", attempt_id=attempt.pk)
    # An older duplicate must not display an active exam interface.
    if is_superseded_active_attempt(attempt):
        return redirect("bcl:exam_rules", module_id=attempt.module_id)

    # HTML-based Listening Module: Serve directly from D:\BCL-Bhuiyan\listening\
    if attempt.module.module_type == ExamModule.ModuleType.LISTENING:
        return render_listening_html(request, attempt)

    sections = list(attempt.module.sections.order_by("order", "pk").prefetch_related("questions__options"))
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
                return redirect("bcl:full_mock_ended", full_attempt_id=full_mock.pk)
            elif attempt.module.module_type == ExamModule.ModuleType.LISTENING:
                full_mock.current_step = "reading"
                full_mock.save(update_fields=["current_step"])
                messages.success(request, "Listening module completed. Next stage: Reading.")
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return JsonResponse({
                        "status": "ok",
                        "raw_score": attempt.raw_score,
                        "band_score": str(attempt.band_score) if attempt.band_score else None,
                        "next_url": reverse("bcl:mock_reading", args=[attempt.module.mock_test_id]),
                    })
                return redirect("bcl:full_mock_intermission", full_attempt_id=full_mock.pk)
            elif attempt.module.module_type == ExamModule.ModuleType.READING:
                full_mock.current_step = "writing"
                full_mock.save(update_fields=["current_step"])
                messages.success(request, "Reading module completed. Next stage: Writing.")
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
        })

    # Objective: Reading or Listening
    if attempt.status != CandidateAttempt.AttemptStatus.IN_PROGRESS and attempt.raw_score is None:
        finalize_attempt_score(attempt)
        attempt.refresh_from_db()
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
        if active_full.current_step == "listening" and active_full.listening_attempt:
            att = expire_attempt_if_needed(active_full.listening_attempt)
            if att.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
                return redirect("bcl:exam_session", attempt_id=att.pk)
            else:
                active_full.current_step = "reading"
                active_full.save(update_fields=["current_step"])
                return redirect("bcl:full_mock_intermission", full_attempt_id=active_full.pk)

        elif active_full.current_step == "reading" and active_full.reading_attempt:
            att = expire_attempt_if_needed(active_full.reading_attempt)
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

        elif active_full.current_step in {"listening", "reading", "writing"}:
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

    listening_module = mock_test.modules.get(module_type=ExamModule.ModuleType.LISTENING, is_active=True)

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
        if full_mock.current_step in {"listening", "reading", "writing"} and not getattr(full_mock, f"{full_mock.current_step}_attempt"):
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


@login_required
def mock_listening_view(request, mock_id):
    """Architecture route: GET /mock/<id>/listening/"""
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
                return redirect("bcl:mock_reading", mock_id=mock_id)

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
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({
                    "status": "ok",
                    "raw_score": completed_attempt.raw_score,
                    "band_score": str(completed_attempt.band_score) if completed_attempt.band_score else None,
                    "next_url": reverse("bcl:mock_reading", args=[mock_id]),
                })
            return redirect("bcl:mock_reading", mock_id=mock_id)
        return JsonResponse({"error": "No active listening attempt found."}, status=404)

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

        # Sequence Guard: Validate Listening is completed
        if not full_mock.listening_attempt or full_mock.listening_attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
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
    mock_id = request.POST.get("mock_id") or request.POST.get("mock_test_id")
    if not mock_id:
        return JsonResponse({"error": "mock_id is required."}, status=400)
    return redirect("bcl:mock_listening", mock_id=mock_id)
