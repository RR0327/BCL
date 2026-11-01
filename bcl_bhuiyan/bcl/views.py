
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from .forms import (
    CandidateRegistrationForm,
    CandidateLoginForm,
)

from .models import (
    IELTSMockTest,
    CandidateAttempt,
    FullMockAttempt,
)


# ==========================================
# IELTS MOCK TEST PLATFORM
# BCL APPLICATION VIEWS
# ==========================================


# ==========================================
# 1. HOMEPAGE
# ==========================================

def home(request):

    modules = [
        {
            "name": "Reading",
            "icon": "📖",
            "description": (
                "Practice IELTS Reading with timed "
                "comprehension questions, passages, "
                "and exam-style navigation."
            ),
            "features": [
                "Split-screen reading",
                "Multiple question types",
                "Timed practice",
            ],
        },
        {
            "name": "Listening",
            "icon": "🎧",
            "description": (
                "Prepare for IELTS Listening with "
                "audio-based practice tests and "
                "realistic examination conditions."
            ),
            "features": [
                "Exam-style audio",
                "Section-based questions",
                "Automatic scoring",
            ],
        },
        {
            "name": "Writing",
            "icon": "✍️",
            "description": (
                "Improve your IELTS Writing skills "
                "through Task 1 and Task 2 practice "
                "with examiner feedback."
            ),
            "features": [
                "Writing Task 1",
                "Writing Task 2",
                "Manual evaluation",
            ],
        },
    ]

    context = {
        "platform_name": getattr(
            settings,
            "APP_NAME",
            "BCL_Bhuiyan"
        ),
        "modules": modules,
    }

    return render(
        request,
        "home.html",
        context,
    )


# ==========================================
# 2. CANDIDATE REGISTRATION
# ==========================================

def candidate_register(request):

    if request.user.is_authenticated:
        return redirect("bcl:dashboard")

    if request.method == "POST":
        form = CandidateRegistrationForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")

            messages.success(
                request,
                "Your account has been created successfully."
            )

            return redirect("bcl:dashboard")

    else:
        form = CandidateRegistrationForm()

    return render(
        request,
        "registration/register.html",
        {
            "form": form,
            "page_title": "Candidate Registration",
        },
    )


# ==========================================
# 3. CANDIDATE LOGIN
# ==========================================

class CandidateLoginView(LoginView):

    template_name = "registration/login.html"

    authentication_form = CandidateLoginForm

    redirect_authenticated_user = True

    def get_success_url(self):
        return self.get_redirect_url() or str(reverse_lazy("bcl:dashboard"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["page_title"] = "Candidate Login"

        return context


# ==========================================
# 4. CANDIDATE LOGOUT
# ==========================================

@require_POST
def candidate_logout(request):

    logout(request)

    messages.success(
        request,
        "You have successfully logged out."
    )

    return redirect("bcl:login")


# ==========================================
# 5. CANDIDATE DASHBOARD
# ==========================================

@login_required
def candidate_dashboard(request):

    candidate = request.user

    mock_tests = (
        IELTSMockTest.objects
        .filter(
            is_published=True,
            modules__is_active=True,
        )
        .distinct()
        .prefetch_related("modules")
        .order_by("test_number")
    )

    recent_attempts = (
        CandidateAttempt.objects
        .filter(candidate=candidate, full_mock__isnull=True)
        .select_related(
            "module",
            "module__mock_test",
        )
        .prefetch_related("task_evaluations")
        .order_by("-started_at")[:10]
    )

    recent_full_mocks = (
        FullMockAttempt.objects
        .filter(candidate=candidate)
        .select_related(
            "mock_test",
            "reading_attempt",
            "listening_attempt",
            "writing_attempt",
        )
        .prefetch_related("writing_attempt__task_evaluations")
        .order_by("-started_at")[:10]
    )

    context = {
        "page_title": "Candidate Dashboard",
        "candidate": candidate,
        "mock_tests": mock_tests,
        "recent_attempts": recent_attempts,
        "recent_full_mocks": recent_full_mocks,
    }

    return render(
        request,
        "candidate/dashboard.html",
        context,
    )
