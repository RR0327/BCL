from django.urls import path
from . import exam_views, views

app_name = "bcl"

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.candidate_register, name="register"),
    path("login/", views.CandidateLoginView.as_view(), name="login"),
    path("logout/", views.candidate_logout, name="logout"),
    path("dashboard/", views.candidate_dashboard, name="dashboard"),
    path("exam/<int:module_id>/rules/", exam_views.exam_rules, name="exam_rules"),
    path("exam/<int:module_id>/start/", exam_views.start_exam, name="start_exam"),
    path("exam/session/<int:attempt_id>/", exam_views.exam_session, name="exam_session"),
    path("exam/session/<int:attempt_id>/timer/", exam_views.exam_timer, name="exam_timer"),
    path("exam/session/<int:attempt_id>/save-answer/", exam_views.save_exam_answer, name="save_exam_answer"),
    path("exam/session/<int:attempt_id>/submit/", exam_views.submit_exam, name="submit_exam"),
    path("exam/session/<int:attempt_id>/result/", exam_views.exam_result, name="exam_result"),
]
