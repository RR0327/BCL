
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


# ==========================================
# IELTS MOCK TEST PLATFORM
# BCL APPLICATION VIEWS
# ==========================================


# ==========================================
# 1. HOMEPAGE
# ==========================================

def home(request):
    """
    Public homepage displaying IELTS practice
    modules and platform information.
    """

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
            "IELTS Mock Test Platform"
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
    """
    Register a new candidate using Django's
    built-in authentication system.
    """

    if request.user.is_authenticated:
        return redirect("bcl:dashboard")

    if request.method == "POST":
        form = CandidateRegistrationForm(
            request.POST
        )

        if form.is_valid():
            user = form.save()

            # Automatically authenticate new user
            login(request, user)

            messages.success(
                request,
                "Your account has been created "
                "successfully. Welcome!"
            )

            return redirect("bcl:dashboard")

    else:
        form = CandidateRegistrationForm()

    context = {
        "form": form,
        "page_title": "Candidate Registration",
    }

    return render(
        request,
        "registration/register.html",
        context,
    )


# ==========================================
# 3. CANDIDATE LOGIN
# ==========================================

class CandidateLoginView(LoginView):
    """
    Candidate login using Django's
    authentication framework.
    """

    template_name = "registration/login.html"

    authentication_form = CandidateLoginForm

    redirect_authenticated_user = True

    def get_success_url(self):
        return str(
            reverse_lazy("bcl:dashboard")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(
            **kwargs
        )

        context["page_title"] = "Candidate Login"

        return context


# ==========================================
# 4. CANDIDATE LOGOUT
# ==========================================

@require_POST
def candidate_logout(request):
    """
    Secure logout through a POST request.
    """

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
    """
    Protected dashboard accessible only
    to authenticated users.

    Exam statistics will be connected
    after implementing database models.
    """

    candidate = request.user

    modules = [
        {
            "name": "Reading",
            "icon": "📖",
            "description": (
                "Practice IELTS Reading "
                "in a timed environment."
            ),
            "status": "Coming Soon",
        },
        {
            "name": "Listening",
            "icon": "🎧",
            "description": (
                "Practice listening with "
                "IELTS-style audio tests."
            ),
            "status": "Coming Soon",
        },
        {
            "name": "Writing",
            "icon": "✍️",
            "description": (
                "Complete IELTS Writing "
                "Task 1 and Task 2."
            ),
            "status": "Coming Soon",
        },
    ]

    context = {
        "page_title": "Candidate Dashboard",
        "candidate": candidate,
        "modules": modules,
    }

    return render(
        request,
        "candidate/dashboard.html",
        context,
    )
