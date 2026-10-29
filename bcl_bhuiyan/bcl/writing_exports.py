"""Staff-only exports for completed IELTS Writing attempts.

PDF uses ReportLab for portability; DOCX uses python-docx. Files are generated
in memory, and candidate responses are never written to temporary public files.
"""
from io import BytesIO
from xml.sax.saxutils import escape

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from .models import CandidateAttempt, CandidateAnswer, ExamModule, get_writing_task_questions
from .writing_views import writing_result_band


def get_export_data(attempt_id):
    attempt = get_object_or_404(
        CandidateAttempt.objects.select_related("candidate", "module__mock_test"),
        pk=attempt_id, module__module_type=ExamModule.ModuleType.WRITING,
    )
    if attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
        from django.http import Http404
        raise Http404("An active Writing attempt cannot be exported.")
    questions = get_writing_task_questions(attempt.module)
    answers = {a.question_id: a.answer_text for a in CandidateAnswer.objects.filter(
        attempt=attempt, question_id__in=[q.pk for q in questions]
    )}
    evaluations = {e.task_number: e for e in attempt.task_evaluations.select_related("examiner")}
    tasks = []
    for n in (1, 2):
        q = questions[n - 1] if len(questions) == 2 else None
        tasks.append({"number": n, "prompt": q.question_text if q else "Task not configured uniquely",
                      "response": answers.get(q.pk, "") if q else "", "evaluation": evaluations.get(n)})
    return attempt, tasks, writing_result_band(attempt)


def export_lines(attempt, tasks, band):
    lines = ["IELTS Writing Submission and Examiner Report",
             f"Attempt: {attempt.pk}", f"Candidate: {attempt.candidate.username}",
             f"Mock test: {attempt.module.mock_test.title}",
             f"Status: {attempt.get_status_display()}",
             f"Submitted: {attempt.submitted_at.isoformat() if attempt.submitted_at else 'Not recorded'}",
             f"Overall practice Writing band: {band if band is not None else 'Pending'}",
             "Practice assessment only; not an official IELTS score."]
    for task in tasks:
        lines += ["", f"WRITING TASK {task['number']}", "Prompt:", task["prompt"],
                  "Candidate response:", task["response"] or "[No response submitted]"]
        e = task["evaluation"]
        if e:
            lines += [f"Examiner: {e.examiner.username}",
                      f"Task Achievement/Response: {e.task_achievement}",
                      f"Coherence and Cohesion: {e.coherence_cohesion}",
                      f"Lexical Resource: {e.lexical_resource}",
                      f"Grammatical Range and Accuracy: {e.grammatical_range_accuracy}",
                      f"Criterion average: {e.criterion_average}",
                      "Examiner feedback:", e.feedback or "[No feedback]"]
        else:
            lines.append("Examiner evaluation: Pending")
    return lines


@staff_member_required
@require_GET
def writing_export(request, attempt_id, format):
    if format not in ("pdf", "docx"):
        from django.http import Http404
        raise Http404("Unsupported export format")
    attempt, tasks, band = get_export_data(attempt_id)
    lines = export_lines(attempt, tasks, band)
    buffer = BytesIO()
    if format == "docx":
        from docx import Document
        from docx.shared import Pt
        doc = Document()
        doc.add_heading(lines[0], 0)
        for line in lines[1:]:
            if line.startswith("WRITING TASK "):
                doc.add_heading(line, level=1)
            else:
                paragraph = doc.add_paragraph(line)
                paragraph.style.font.size = Pt(10)
        doc.save(buffer)
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether
        styles = getSampleStyleSheet()
        body = ParagraphStyle("ExportBody", parent=styles["BodyText"], fontSize=9,
                              leading=13, spaceAfter=7, alignment=TA_LEFT, wordWrap="CJK")
        heading = ParagraphStyle("ExportHeading", parent=styles["Heading2"],
                                 textColor=colors.HexColor("#173a78"), spaceBefore=12)
        story = []
        for i, line in enumerate(lines):
            style = styles["Title"] if i == 0 else heading if line.startswith("WRITING TASK ") else body
            # Paragraph requires escaped XML; preserve line breaks and prevent markup injection.
            safe = escape(line).replace("\n", "<br/>") or "&#160;"
            story.append(Paragraph(safe, style))
        SimpleDocTemplate(buffer, pagesize=A4, leftMargin=45, rightMargin=45,
                          topMargin=48, bottomMargin=48, title="IELTS Writing Report").build(story)
        content_type = "application/pdf"
    response = HttpResponse(buffer.getvalue(), content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="writing_attempt_{attempt.pk}.{format}"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
