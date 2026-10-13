
from django.urls import path

from . import views


# ==========================================
# IELTS MOCK TEST PLATFORM
# BCL APPLICATION URL CONFIGURATION
# ==========================================

app_name = "bcl"


urlpatterns = [

    # ======================================
    # 1. PUBLIC HOMEPAGE
    # ======================================

    path(
        "",
        views.home,
        name="home",
    ),


    # ======================================
    # 2. CANDIDATE REGISTRATION
    # ======================================

    path(
        "register/",
        views.candidate_register,
        name="register",
    ),


    # ======================================
    # 3. CANDIDATE LOGIN
    # ======================================

    path(
        "login/",
        views.CandidateLoginView.as_view(),
        name="login",
    ),


    # ======================================
    # 4. CANDIDATE LOGOUT
    # ======================================

    path(
        "logout/",
        views.candidate_logout,
        name="logout",
    ),


    # ======================================
    # 5. CANDIDATE DASHBOARD
    # ======================================

    path(
        "dashboard/",
        views.candidate_dashboard,
        name="dashboard",
    ),

]
