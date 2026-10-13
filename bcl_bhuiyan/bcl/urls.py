
from django.urls import path

from . import views
from . import exam_views


# ==========================================
# IELTS MOCK TEST PLATFORM
# COMPLETE BCL URL CONFIGURATION
# ==========================================

app_name = "bcl"


urlpatterns = [

    # ======================================
    # PUBLIC HOMEPAGE
    # ======================================

    path(
        "",
        views.home,
        name="home",
    ),

    # ======================================
    # CANDIDATE AUTHENTICATION
    # ======================================

    path(
        "register/",
        views.candidate_register,
        name="register",
    ),

    path(
        "login/",
        views.CandidateLoginView.as_view(),
        name="login",
    ),

    path(
        "logout/",
        views.candidate_logout,
        name="logout",
    ),

    # ======================================
    # CANDIDATE DASHBOARD
    # ======================================

    path(
        "dashboard/",
        views.candidate_dashboard,
        name="dashboard",
    ),

    # ======================================
    # EXAMINATION RULES
    # ======================================

    path(
        "exam/<int:module_id>/rules/",
        exam_views.exam_rules,
        name="exam_rules",
    ),

    # ======================================
    # START EXAMINATION
    # ======================================

    path(
        "exam/<int:module_id>/start/",
        exam_views.start_exam,
        name="start_exam",
    ),

    # ======================================
    # EXAMINATION SESSION
    # ======================================

    path(
        "exam/session/<int:attempt_id>/",
        exam_views.exam_session,
        name="exam_session",
    ),

    # ======================================
    # TIMER SYNCHRONIZATION
    # ======================================

    path(
        "exam/session/<int:attempt_id>/timer/",
        exam_views.exam_timer,
        name="exam_timer",
    ),

    # ======================================
    # SUBMIT EXAMINATION
    # ======================================

    path(
        "exam/session/<int:attempt_id>/submit/",
        exam_views.submit_exam,
        name="submit_exam",
    ),

    # ======================================
    # EXAM RESULT STATUS
    # ======================================

    path(
        "exam/session/<int:attempt_id>/result/",
        exam_views.exam_result,
        name="exam_result",
    ),

]
