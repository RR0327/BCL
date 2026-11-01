"""Attempt-scoped, authenticated delivery of private exam attachments."""
import mimetypes
from pathlib import PurePosixPath
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET
from .models import CandidateAttempt, ExamSection, Question


ALLOWED_AUDIO_EXTENSIONS = {"mp3", "wav", "ogg", "m4a", "aac", "webm"}
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}


@login_required
@require_GET
def section_media(request, attempt_id, section_id, kind):
    if kind not in ("audio", "image"):
        raise Http404
    if not request.user.is_active or request.user.is_staff or request.user.is_superuser:
        raise Http404
    attempt = get_object_or_404(CandidateAttempt, pk=attempt_id, candidate=request.user)
    if attempt.status != CandidateAttempt.AttemptStatus.IN_PROGRESS or timezone.now() >= attempt.expires_at:
        raise Http404
    section = get_object_or_404(ExamSection, pk=section_id, module_id=attempt.module_id)
    field = section.audio_file if kind == "audio" else section.image
    if not field or not field.name:
        raise Http404
    if kind == "audio" and field.name.rsplit(".", 1)[-1].lower() not in ALLOWED_AUDIO_EXTENSIONS:
        raise Http404
    try:
        # Storage abstraction keeps authorization independent of the filesystem.
        handle = field.open("rb")
    except (OSError, ValueError, FileNotFoundError):
        raise Http404
    content_type = mimetypes.guess_type(field.name)[0] or "application/octet-stream"
    if kind == "audio" and not content_type.startswith("audio/"):
        content_type = "application/octet-stream"
    if kind == "image" and not content_type.startswith("image/"):
        content_type = "application/octet-stream"
    response = FileResponse(handle, content_type=content_type, as_attachment=False)
    response["Content-Disposition"] = "inline; filename=\"%s\"" % PurePosixPath(field.name).name.replace('"', '')
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    if kind == "audio":
        response["Accept-Ranges"] = "bytes"
    return response


@login_required
@require_GET
def question_media(request, attempt_id, question_id):
    if not request.user.is_active or request.user.is_staff or request.user.is_superuser:
        raise Http404
    attempt = get_object_or_404(CandidateAttempt, pk=attempt_id, candidate=request.user)
    if attempt.status != CandidateAttempt.AttemptStatus.IN_PROGRESS or timezone.now() >= attempt.expires_at:
        raise Http404
    question = get_object_or_404(Question, pk=question_id, section__module_id=attempt.module_id)
    field = question.image
    if not field or not field.name:
        raise Http404
    if field.name.rsplit(".", 1)[-1].lower() not in ALLOWED_IMAGE_EXTENSIONS:
        raise Http404
    try:
        handle = field.open("rb")
    except (OSError, ValueError, FileNotFoundError):
        raise Http404
    content_type = mimetypes.guess_type(field.name)[0] or "application/octet-stream"
    if not content_type.startswith("image/"):
        content_type = "application/octet-stream"
    response = FileResponse(handle, content_type=content_type, as_attachment=False)
    response["Content-Disposition"] = "inline; filename=\"%s\"" % PurePosixPath(field.name).name.replace('"', '')
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


@login_required
@require_GET
def module_media(request, attempt_id, kind):
    if kind not in ("audio", "content"):
        raise Http404
    if not request.user.is_active or request.user.is_staff or request.user.is_superuser:
        raise Http404
    attempt = get_object_or_404(CandidateAttempt, pk=attempt_id, candidate=request.user)
    if attempt.status != CandidateAttempt.AttemptStatus.IN_PROGRESS or timezone.now() >= attempt.expires_at:
        raise Http404
    field = (
        attempt.module.audio_file
        if kind == "audio"
        else (
            getattr(attempt.module, "module_file", None)
            or getattr(attempt.module, "content_file", None)
        )
    )
    if not field or not field.name:
        raise Http404
    if kind == "audio" and field.name.rsplit(".", 1)[-1].lower() not in ALLOWED_AUDIO_EXTENSIONS:
        raise Http404
    try:
        handle = field.open("rb")
    except (OSError, ValueError, FileNotFoundError):
        raise Http404
    content_type = mimetypes.guess_type(field.name)[0] or "application/octet-stream"
    if kind == "audio" and not content_type.startswith("audio/"):
        content_type = "application/octet-stream"
    response = FileResponse(handle, content_type=content_type, as_attachment=False)
    response["Content-Disposition"] = "inline; filename=\"%s\"" % PurePosixPath(field.name).name.replace('"', '')
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    if kind == "audio":
        response["Accept-Ranges"] = "bytes"
    return response


@login_required
@require_GET
def review_section_media(request, attempt_id, section_id, kind):
    if kind not in ("audio", "image"):
        raise Http404
    if not request.user.is_active:
        raise Http404
    attempt = get_object_or_404(CandidateAttempt, pk=attempt_id)
    if attempt.candidate != request.user and not request.user.is_staff and not request.user.is_superuser:
        raise Http404
    if attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
        raise Http404
    section = get_object_or_404(ExamSection, pk=section_id, module_id=attempt.module_id)
    field = section.audio_file if kind == "audio" else section.image
    if not field or not field.name:
        raise Http404
    try:
        handle = field.open("rb")
    except (OSError, ValueError, FileNotFoundError):
        raise Http404
    content_type = mimetypes.guess_type(field.name)[0] or "application/octet-stream"
    response = FileResponse(handle, content_type=content_type, as_attachment=False)
    response["Content-Disposition"] = "inline; filename=\"%s\"" % PurePosixPath(field.name).name.replace('"', '')
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["X-Content-Type-Options"] = "nosniff"
    if kind == "audio":
        response["Accept-Ranges"] = "bytes"
    return response


@login_required
@require_GET
def review_module_media(request, attempt_id, kind):
    if kind not in ("audio",):
        raise Http404
    if not request.user.is_active:
        raise Http404
    attempt = get_object_or_404(CandidateAttempt, pk=attempt_id)
    if attempt.candidate != request.user and not request.user.is_staff and not request.user.is_superuser:
        raise Http404
    if attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
        raise Http404
    field = attempt.module.audio_file
    if not field or not field.name:
        raise Http404
    try:
        handle = field.open("rb")
    except (OSError, ValueError, FileNotFoundError):
        raise Http404
    content_type = mimetypes.guess_type(field.name)[0] or "application/octet-stream"
    response = FileResponse(handle, content_type=content_type, as_attachment=False)
    response["Content-Disposition"] = "inline; filename=\"%s\"" % PurePosixPath(field.name).name.replace('"', '')
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["X-Content-Type-Options"] = "nosniff"
    if kind == "audio":
        response["Accept-Ranges"] = "bytes"
    return response


@login_required
@require_GET
def review_question_media(request, attempt_id, question_id):
    if not request.user.is_active:
        raise Http404
    attempt = get_object_or_404(CandidateAttempt, pk=attempt_id)
    if attempt.candidate != request.user and not request.user.is_staff and not request.user.is_superuser:
        raise Http404
    if attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
        raise Http404
    question = get_object_or_404(Question, pk=question_id, section__module_id=attempt.module_id)
    field = question.image
    if not field or not field.name:
        raise Http404
    try:
        handle = field.open("rb")
    except (OSError, ValueError, FileNotFoundError):
        raise Http404
    content_type = mimetypes.guess_type(field.name)[0] or "application/octet-stream"
    response = FileResponse(handle, content_type=content_type, as_attachment=False)
    response["Content-Disposition"] = "inline; filename=\"%s\"" % PurePosixPath(field.name).name.replace('"', '')
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_GET
def staff_section_image(request, attempt_id, section_id):
    if not request.user.is_active or not request.user.is_staff:
        raise Http404
    attempt = get_object_or_404(CandidateAttempt, pk=attempt_id, module__module_type="writing")
    if attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
        raise Http404
    section = get_object_or_404(ExamSection, pk=section_id, module_id=attempt.module_id)
    if not section.image or not section.image.name:
        raise Http404
    try:
        handle = section.image.open("rb")
    except (OSError, ValueError, FileNotFoundError):
        raise Http404
    response = FileResponse(handle, content_type=mimetypes.guess_type(section.image.name)[0] or "application/octet-stream")
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["X-Content-Type-Options"] = "nosniff"
    return response
