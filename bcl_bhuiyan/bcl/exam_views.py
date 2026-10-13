
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import (
    ExamModule,
    CandidateAttempt,
)


# ==========================================
# IELTS MOCK TEST PLATFORM
# PHASE 2 - EXAMINATION ENGINE
# ==========================================


# ==========================================
# 1. CANDIDATE PERMISSION CHECK
# ==========================================

def is_candidate(user):
    """
    Check whether the authenticated user
    is allowed to take candidate exams.

    Staff and superuser accounts cannot
    participate as candidates.
    """

    return (
        user.is_authenticated
        and user.is_active
        and not user.is_staff
        and not user.is_superuser
    )


# ==========================================
# 2. SERVER-SIDE TIME CALCULATION
# ==========================================

def get_remaining_seconds(attempt, now=None):
    """
    Calculate remaining examination time
    based on the server clock.

    Client-side time manipulation cannot
    extend the server deadline.
    """

    now = now or timezone.now()

    remaining = (
        attempt.expires_at - now
    ).total_seconds()

    return max(0, int(remaining))


# ==========================================
# 3. AUTOMATIC EXPIRY HANDLING
# ==========================================

def expire_attempt_if_needed(attempt):
    """
    Automatically end an active examination
    if its server-side deadline has passed.

    This function is called when the server
    processes requests involving an attempt.
    """

    with transaction.atomic():

        locked_attempt = (
            CandidateAttempt.objects
            .select_for_update()
            .get(pk=attempt.pk)
        )

        now = timezone.now()

        if (
            locked_attempt.status
            == CandidateAttempt.AttemptStatus.IN_PROGRESS
            and now >= locked_attempt.expires_at
        ):

            locked_attempt.status = (
                CandidateAttempt.AttemptStatus.AUTO_SUBMITTED
            )

            locked_attempt.submitted_at = now

            locked_attempt.save(
                update_fields=[
                    "status",
                    "submitted_at",
                ]
            )

        return locked_attempt


# ==========================================
# 4. SECURE CANDIDATE ATTEMPT LOOKUP
# ==========================================

def get_candidate_attempt(request, attempt_id):
    """
    Retrieve an exam attempt belonging
    to the currently authenticated user.

    Other candidates cannot view
    another user's examination session.
    """

    return get_object_or_404(
        CandidateAttempt.objects.select_related(
            "module",
            "module__mock_test",
        ),
        pk=attempt_id,
        candidate=request.user,
    )


# ==========================================
# 5. EXAMINATION RULES
# ==========================================

@login_required
@require_GET
def exam_rules(request, module_id):
    """
    Display examination instructions
    before the candidate starts a test.
    """

    if not is_candidate(request.user):

        messages.error(
            request,
            "Administrator accounts cannot "
            "take candidate examinations."
        )

        return redirect("bcl:dashboard")

    module = get_object_or_404(
        ExamModule.objects.select_related(
            "mock_test"
        ),
        pk=module_id,
        is_active=True,
        mock_test__is_published=True,
    )

    active_attempts = (
        CandidateAttempt.objects
        .filter(
            candidate=request.user,
            module=module,
            status=(
                CandidateAttempt.AttemptStatus.IN_PROGRESS
            ),
        )
        .order_by("-started_at")
    )

    for active_attempt in active_attempts:

        updated_attempt = expire_attempt_if_needed(
            active_attempt
        )

        if (
            updated_attempt.status
            == CandidateAttempt.AttemptStatus.IN_PROGRESS
        ):

            return redirect(
                "bcl:exam_session",
                attempt_id=updated_attempt.pk,
            )

    context = {
        "module": module,
        "mock_test": module.mock_test,
    }

    return render(
        request,
        "exam/rules.html",
        context,
    )


# ==========================================
# 6. START OR RESUME EXAMINATION
# ==========================================

@login_required
@require_POST
def start_exam(request, module_id):
    """
    Start a new examination attempt.

    If a valid active attempt already exists,
    resume that attempt instead.

    The exam deadline is calculated
    using the server's current time.
    """

    # --------------------------------------
    # Candidate authentication
    # --------------------------------------

    if not is_candidate(request.user):

        messages.error(
            request,
            "This action is only available "
            "to candidates."
        )

        return redirect("bcl:dashboard")

    # --------------------------------------
    # Verify exam rules acknowledgement
    # --------------------------------------

    if request.POST.get("accept_rules") != "yes":

        messages.error(
            request,
            "You must accept the "
            "examination rules before starting."
        )

        return redirect(
            "bcl:exam_rules",
            module_id=module_id,
        )

    # --------------------------------------
    # Retrieve published exam module
    # --------------------------------------

    module = get_object_or_404(
        ExamModule.objects.select_related(
            "mock_test"
        ),
        pk=module_id,
        is_active=True,
        mock_test__is_published=True,
    )

    # --------------------------------------
    # Begin database transaction
    # --------------------------------------

    with transaction.atomic():

        # FIX:
        # Use Django's real User model instead of
        # type(request.user), which may return
        # SimpleLazyObject.

        User = get_user_model()

        User.objects.select_for_update().get(
            pk=request.user.pk
        )

        # ----------------------------------
        # Find existing active attempts
        # ----------------------------------

        existing_attempts = (
            CandidateAttempt.objects
            .filter(
                candidate=request.user,
                module=module,
                status=(
                    CandidateAttempt.AttemptStatus.IN_PROGRESS
                ),
            )
            .order_by("-started_at")
        )

        active_attempt = None

        now = timezone.now()

        for attempt in existing_attempts:

            # Expire outdated attempts
            if now >= attempt.expires_at:

                attempt.status = (
                    CandidateAttempt.AttemptStatus.AUTO_SUBMITTED
                )

                attempt.submitted_at = now

                attempt.save(
                    update_fields=[
                        "status",
                        "submitted_at",
                    ]
                )

            elif active_attempt is None:

                active_attempt = attempt

        # ----------------------------------
        # Resume existing attempt
        # ----------------------------------

        if active_attempt is not None:

            exam_attempt = active_attempt

        # ----------------------------------
        # Create a new attempt
        # ----------------------------------

        else:

            exam_attempt = CandidateAttempt.objects.create(
                candidate=request.user,
                module=module,
                started_at=now,
                expires_at=(
                    now + timedelta(
                        minutes=module.duration_minutes
                    )
                ),
                status=(
                    CandidateAttempt.AttemptStatus.IN_PROGRESS
                ),
            )

    return redirect(
        "bcl:exam_session",
        attempt_id=exam_attempt.pk,
    )


# ==========================================
# 7. EXAMINATION SESSION PAGE
# ==========================================

@login_required
@require_GET
def exam_session(request, attempt_id):
    """
    Display the candidate's examination
    session and current countdown.
    """

    attempt = get_candidate_attempt(
        request,
        attempt_id,
    )

    attempt = expire_attempt_if_needed(
        attempt
    )

    # Prevent reopening a completed exam
    if (
        attempt.status
        != CandidateAttempt.AttemptStatus.IN_PROGRESS
    ):

        return redirect(
            "bcl:exam_result",
            attempt_id=attempt.pk,
        )

    remaining_seconds = get_remaining_seconds(
        attempt
    )

    sections = (
        attempt.module.sections
        .prefetch_related("questions")
        .order_by("order")
    )

    context = {
        "attempt": attempt,
        "module": attempt.module,
        "mock_test": attempt.module.mock_test,
        "sections": sections,
        "remaining_seconds": remaining_seconds,
    }

    return render(
        request,
        "exam/session.html",
        context,
    )


# ==========================================
# 8. SERVER TIMER SYNCHRONIZATION API
# ==========================================

@login_required
@require_GET
def exam_timer(request, attempt_id):
    """
    Return server-calculated remaining time
    and the current exam status.
    """

    attempt = get_candidate_attempt(
        request,
        attempt_id,
    )

    attempt = expire_attempt_if_needed(
        attempt
    )

    if (
        attempt.status
        == CandidateAttempt.AttemptStatus.IN_PROGRESS
    ):

        remaining_seconds = get_remaining_seconds(
            attempt
        )

    else:

        remaining_seconds = 0

    return JsonResponse({
        "attempt_id": attempt.pk,
        "status": attempt.status,
        "remaining_seconds": remaining_seconds,
        "server_time": timezone.now().isoformat(),
        "expires_at": attempt.expires_at.isoformat(),
        "violation_count": attempt.violation_count,
    })


# ==========================================
# 9. MANUAL EXAMINATION SUBMISSION
# ==========================================

@login_required
@require_POST
def submit_exam(request, attempt_id):
    """
    End the candidate's exam session.

    If the deadline has already passed,
    the attempt is automatically submitted.
    """

    if not is_candidate(request.user):

        return JsonResponse(
            {
                "error": (
                    "Only candidates can "
                    "submit examinations."
                )
            },
            status=403,
        )

    with transaction.atomic():

        attempt = get_object_or_404(
            CandidateAttempt.objects
            .select_for_update(),
            pk=attempt_id,
            candidate=request.user,
        )

        if (
            attempt.status
            == CandidateAttempt.AttemptStatus.IN_PROGRESS
        ):

            now = timezone.now()

            if now >= attempt.expires_at:

                attempt.status = (
                    CandidateAttempt.AttemptStatus.AUTO_SUBMITTED
                )

            else:

                attempt.status = (
                    CandidateAttempt.AttemptStatus.SUBMITTED
                )

            attempt.submitted_at = now

            attempt.save(
                update_fields=[
                    "status",
                    "submitted_at",
                ]
            )

    messages.success(
        request,
        "Your examination session has ended."
    )

    return redirect(
        "bcl:exam_result",
        attempt_id=attempt.pk,
    )


# ==========================================
# 10. EXAM RESULT / STATUS PAGE
# ==========================================

@login_required
@require_GET
def exam_result(request, attempt_id):
    """
    Display the finished examination
    status for the attempt owner.
    """

    attempt = get_candidate_attempt(
        request,
        attempt_id,
    )

    attempt = expire_attempt_if_needed(
        attempt
    )

    if (
        attempt.status
        == CandidateAttempt.AttemptStatus.IN_PROGRESS
    ):

        return redirect(
            "bcl:exam_session",
            attempt_id=attempt.pk,
        )

    context = {
        "attempt": attempt,
    }

    return render(
        request,
        "exam/result.html",
        context,
    )
