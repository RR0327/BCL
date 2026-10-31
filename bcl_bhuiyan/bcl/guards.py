from functools import wraps
from django.contrib import messages
from django.db import models
from django.shortcuts import get_object_or_404, redirect
from .models import CandidateAttempt, FullMockAttempt


def full_mock_sequence_guard(required_step):
    """
    Enforces server-side sequence for sequential full mock exams:
    Stage 1: listening -> listening_done
    Stage 2: reading -> reading_done
    Stage 3: writing -> completed
    
    If candidate tries to bypass (e.g. going directly to reading while listening is unfinished),
    it blocks and redirects back to their active incomplete stage.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, mock_id, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("bcl:login")

            # Resolve full mock by mock_test_id or full_mock_id
            full_mock = (
                FullMockAttempt.objects.select_related("mock_test", "listening_attempt", "reading_attempt", "writing_attempt")
                .filter(candidate=request.user)
                .filter(models.Q(mock_test_id=mock_id) | models.Q(pk=mock_id))
                .order_by("-started_at")
                .first()
            )

            if not full_mock:
                # If no full mock session exists, redirect to start listening
                messages.warning(request, "Starting mock exam from Stage 1: Listening.")
                return redirect("bcl:mock_listening", mock_id=mock_id)

            resolved_mock_id = full_mock.mock_test_id

            # Mapping of step to appropriate GET URL
            step_redirect_map = {
                "listening": f"/mock/{resolved_mock_id}/listening/",
                "listening_done": f"/mock/{resolved_mock_id}/listening/complete/",
                "reading": f"/mock/{resolved_mock_id}/reading/",
                "reading_done": f"/mock/{resolved_mock_id}/reading/complete/",
                "writing": f"/mock/{resolved_mock_id}/writing/",
                "completed": f"/mock/{resolved_mock_id}/consolidated-result/",
            }

            current_step = full_mock.current_step or "listening"

            # Check if current_step matches required_step
            if current_step != required_step:
                target_url = step_redirect_map.get(current_step, f"/mock/{resolved_mock_id}/listening/")
                messages.warning(request, "Sequence enforcement: Returning to your active exam stage.")
                return redirect(target_url)

            return view_func(request, mock_id, *args, **kwargs)
        return _wrapped
    return decorator


def attempt_ownership_guard(view_func):
    """Validates that candidate owns the attempt and that it belongs to them."""
    @wraps(view_func)
    def _wrapped(request, attempt_id, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("bcl:login")
        attempt = get_object_or_404(
            CandidateAttempt.objects.select_related("module__mock_test"),
            pk=attempt_id,
            candidate=request.user
        )
        return view_func(request, attempt, *args, **kwargs)
    return _wrapped
