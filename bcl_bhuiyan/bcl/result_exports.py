"""Staff-only exports for IELTS candidate exam results (Reading, Listening, Writing, Full Mock).

Supports:
- Individual module attempts (Reading, Listening, Writing) as PDF & DOCX.
- Complete All-Module Full Mock attempts as combined PDF & DOCX reports.
Generated in memory with ReportLab and python-docx.
"""
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import (
    CandidateAttempt,
    CandidateAnswer,
    ExamModule,
    FullMockAttempt,
    Question,
    get_writing_task_questions,
)
from .writing_views import writing_result_band


def format_local_dt(dt, fmt="%Y-%m-%d %H:%M"):
    if not dt:
        return "—"
    if timezone.is_aware(dt):
        dt = timezone.localtime(dt)
    return dt.strftime(fmt)


# ==============================================================================
# 1. INDIVIDUAL MODULE RESULT EXPORT (READING, LISTENING, WRITING)
# ==============================================================================

def get_module_attempt_data(attempt_id):
    attempt = get_object_or_404(
        CandidateAttempt.objects.select_related("candidate", "module__mock_test"),
        pk=attempt_id,
    )
    if attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
        raise Http404("Active attempts cannot be exported until completed.")

    module = attempt.module
    mock_test = module.mock_test
    module_type = module.module_type

    sections = list(module.sections.order_by("order", "pk").prefetch_related("questions__options"))
    answers = {a.question_id: a for a in CandidateAnswer.objects.filter(attempt=attempt)}

    questions_data = []
    correct_count = 0
    wrong_count = 0
    global_num = 1

    for section in sections:
        for q in section.questions.order_by("order", "pk"):
            ans = answers.get(q.pk)
            candidate_answer = ans.answer_text if ans else ""
            is_correct = bool(ans and ans.is_correct)
            is_blank = not bool(candidate_answer.strip())

            if is_correct:
                correct_count += 1
            else:
                wrong_count += 1

            questions_data.append({
                "global_num": global_num,
                "section_title": section.title,
                "question_text": q.question_text,
                "question_type": q.get_question_type_display(),
                "candidate_answer": candidate_answer or "[No Answer]",
                "correct_answer": q.correct_answer or "—",
                "is_correct": is_correct,
                "is_blank": is_blank,
                "explanation": q.explanation or "",
            })
            global_num += 1

    # For writing modules
    writing_tasks = []
    writing_band = None
    if module_type == ExamModule.ModuleType.WRITING:
        writing_band = writing_result_band(attempt)
        evaluations = {e.task_number: e for e in attempt.task_evaluations.select_related("examiner")}
        essay_questions = get_writing_task_questions(module)
        for n in (1, 2):
            q = essay_questions[n - 1] if len(essay_questions) == 2 else None
            resp = answers.get(q.pk).answer_text if (q and q.pk in answers) else ""
            writing_tasks.append({
                "task_number": n,
                "title": f"Writing Task {n}",
                "prompt": q.question_text if q else "Task prompt not configured",
                "response": resp or "[No response submitted]",
                "word_count": len(resp.strip().split()) if resp.strip() else 0,
                "evaluation": evaluations.get(n),
            })

    duration_str = "—"
    if attempt.started_at and attempt.submitted_at:
        seconds = max(0, int((attempt.submitted_at - attempt.started_at).total_seconds()))
        duration_str = f"{seconds // 60}m {seconds % 60}s"

    return {
        "attempt": attempt,
        "module": module,
        "mock_test": mock_test,
        "module_type": module_type,
        "questions_data": questions_data,
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "total_questions": len(questions_data),
        "raw_score": attempt.raw_score,
        "band_score": attempt.band_score,
        "duration_str": duration_str,
        "writing_tasks": writing_tasks,
        "writing_band": writing_band,
    }


@staff_member_required
@require_GET
def export_candidate_attempt(request, attempt_id, format):
    if format not in ("pdf", "docx"):
        raise Http404("Unsupported export format.")

    data = get_module_attempt_data(attempt_id)
    attempt = data["attempt"]
    module_type = data["module_type"]

    buffer = BytesIO()

    if format == "docx":
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT

        doc = Document()

        # Title
        title_p = doc.add_heading(f"IELTS {module_type.capitalize()} Assessment Report", 0)
        title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Candidate & Exam Info Table
        table = doc.add_table(rows=5, cols=2)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        info_rows = [
            ("Candidate Name:", f"{attempt.candidate.get_full_name() or attempt.candidate.username} ({attempt.candidate.email})"),
            ("Mock Examination:", f"{data['mock_test'].title}"),
            ("Module:", f"{module_type.capitalize()} Module"),
            ("Date & Time Submitted:", f"{format_local_dt(attempt.submitted_at) if attempt.submitted_at else 'In Progress'} (Time: {data['duration_str']})"),
            ("Final Result:", f"Band Score: {attempt.band_score if attempt.band_score is not None else 'Pending'} | Raw Score: {attempt.raw_score}/{data['total_questions']}" if module_type != "writing" else f"Writing Band: {data['writing_band'] if data['writing_band'] is not None else 'Pending Review'}"),
        ]
        for idx, (label, val) in enumerate(info_rows):
            r = table.rows[idx]
            r.cells[0].paragraphs[0].add_run(label).bold = True
            r.cells[1].paragraphs[0].add_run(val)

        doc.add_paragraph()

        # Content based on module type
        if module_type == "writing":
            for task in data["writing_tasks"]:
                doc.add_heading(f"Writing Task {task['task_number']}", level=1)
                p_prompt = doc.add_paragraph()
                p_prompt.add_run("Task Prompt: ").bold = True
                p_prompt.add_run(task["prompt"])

                p_resp = doc.add_paragraph()
                p_resp.add_run(f"Candidate Response ({task['word_count']} words):\n").bold = True
                p_resp.add_run(task["response"])

                ev = task["evaluation"]
                if ev:
                    doc.add_heading(f"Examiner Evaluation (Graded by {ev.examiner.username}):", level=2)
                    ev_table = doc.add_table(rows=5, cols=2)
                    ev_rows = [
                        ("Task Achievement / Response:", str(ev.task_achievement)),
                        ("Coherence & Cohesion:", str(ev.coherence_cohesion)),
                        ("Lexical Resource:", str(ev.lexical_resource)),
                        ("Grammatical Range & Accuracy:", str(ev.grammatical_range_accuracy)),
                        ("Criterion Average:", str(ev.criterion_average)),
                    ]
                    for eidx, (lbl, val) in enumerate(ev_rows):
                        r = ev_table.rows[eidx]
                        r.cells[0].paragraphs[0].add_run(lbl).bold = True
                        r.cells[1].paragraphs[0].add_run(val)
                    if ev.feedback:
                        p_fb = doc.add_paragraph()
                        p_fb.add_run("Examiner Feedback:\n").bold = True
                        p_fb.add_run(ev.feedback)
                else:
                    doc.add_paragraph("Examiner Evaluation: Pending review by examiner.")
                doc.add_paragraph()

        else:
            # Objective: Reading or Listening questions table
            doc.add_heading(f"Question by Question Detailed Performance", level=1)
            q_table = doc.add_table(rows=1, cols=5)
            q_table.alignment = WD_TABLE_ALIGNMENT.CENTER
            hdr = q_table.rows[0].cells
            hdr[0].paragraphs[0].add_run("#").bold = True
            hdr[1].paragraphs[0].add_run("Part").bold = True
            hdr[2].paragraphs[0].add_run("Candidate Answer").bold = True
            hdr[3].paragraphs[0].add_run("Correct Answer").bold = True
            hdr[4].paragraphs[0].add_run("Status").bold = True

            for q in data["questions_data"]:
                row_cells = q_table.add_row().cells
                row_cells[0].paragraphs[0].add_run(str(q["global_num"]))
                row_cells[1].paragraphs[0].add_run(q["section_title"][:15])
                row_cells[2].paragraphs[0].add_run(q["candidate_answer"])
                row_cells[3].paragraphs[0].add_run(q["correct_answer"])
                status_text = "✓ Correct" if q["is_correct"] else ("— Blank" if q["is_blank"] else "✗ Incorrect")
                row_cells[4].paragraphs[0].add_run(status_text)

        doc.add_paragraph("\nReport generated by IELTS Bhuiyan Portal. Practice assessment only; not an official IELTS TRF.")
        doc.save(buffer)
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    else:
        # PDF generation using ReportLab
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=18, leading=22, textColor=colors.HexColor("#1e3a8a"))
        h1_style = ParagraphStyle("Heading1", parent=styles["Heading2"], fontSize=13, leading=16, textColor=colors.HexColor("#1e40af"), spaceBefore=10, spaceAfter=6)
        body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9, leading=12, textColor=colors.HexColor("#1f2937"))
        cell_style = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=8, leading=10)

        story = []
        story.append(Paragraph(f"IELTS {module_type.capitalize()} Candidate Assessment Report", title_style))
        story.append(Spacer(1, 10))

        # Candidate Summary Table
        summary_data = [
            [Paragraph("<b>Candidate:</b>", body_style), Paragraph(f"{attempt.candidate.get_full_name() or attempt.candidate.username} ({attempt.candidate.email})", body_style)],
            [Paragraph("<b>Mock Test:</b>", body_style), Paragraph(data["mock_test"].title, body_style)],
            [Paragraph("<b>Module:</b>", body_style), Paragraph(f"{module_type.capitalize()} (Duration: {data['duration_str']})", body_style)],
            [Paragraph("<b>Submitted:</b>", body_style), Paragraph(format_local_dt(attempt.submitted_at) if attempt.submitted_at else 'In Progress', body_style)],
            [Paragraph("<b>Score:</b>", body_style), Paragraph(f"<b>Band {attempt.band_score}</b> (Raw: {attempt.raw_score}/{data['total_questions']})" if module_type != "writing" else f"<b>Writing Band: {data['writing_band'] or 'Pending'}</b>", body_style)],
        ]
        sum_table = Table(summary_data, colWidths=[100, 400])
        sum_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(sum_table)
        story.append(Spacer(1, 14))

        if module_type == "writing":
            for task in data["writing_tasks"]:
                story.append(Paragraph(f"<b>Writing Task {task['task_number']}</b>", h1_style))
                story.append(Paragraph(f"<b>Prompt:</b> {escape(task['prompt'])}", body_style))
                story.append(Spacer(1, 4))
                resp_text = escape(task["response"]).replace("\n", "<br/>") or "[No response submitted]"
                story.append(Paragraph(f"<b>Candidate Essay ({task['word_count']} words):</b><br/>{resp_text}", body_style))
                story.append(Spacer(1, 6))

                ev = task["evaluation"]
                if ev:
                    ev_rows = [
                        [Paragraph("<b>Criteria</b>", cell_style), Paragraph("<b>Score (0-9)</b>", cell_style)],
                        [Paragraph("Task Achievement / Response", cell_style), Paragraph(str(ev.task_achievement), cell_style)],
                        [Paragraph("Coherence and Cohesion", cell_style), Paragraph(str(ev.coherence_cohesion), cell_style)],
                        [Paragraph("Lexical Resource", cell_style), Paragraph(str(ev.lexical_resource), cell_style)],
                        [Paragraph("Grammatical Range & Accuracy", cell_style), Paragraph(str(ev.grammatical_range_accuracy), cell_style)],
                        [Paragraph("<b>Criterion Average</b>", cell_style), Paragraph(f"<b>{ev.criterion_average}</b>", cell_style)],
                    ]
                    t_ev = Table(ev_rows, colWidths=[250, 100])
                    t_ev.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e0e7ff")),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                        ('PADDING', (0, 0), (-1, -1), 4),
                    ]))
                    story.append(t_ev)
                    if ev.feedback:
                        story.append(Spacer(1, 4))
                        story.append(Paragraph(f"<b>Examiner Feedback:</b> {escape(ev.feedback)}", body_style))
                else:
                    story.append(Paragraph("<i>Examiner Evaluation: Pending manual review.</i>", body_style))
                story.append(Spacer(1, 10))

        else:
            story.append(Paragraph("<b>Question Performance Details</b>", h1_style))
            table_rows = [
                [Paragraph("<b>#</b>", cell_style), Paragraph("<b>Part</b>", cell_style), Paragraph("<b>Candidate Answer</b>", cell_style), Paragraph("<b>Correct Answer</b>", cell_style), Paragraph("<b>Result</b>", cell_style)]
            ]
            for q in data["questions_data"]:
                status_color = "#16a34a" if q["is_correct"] else ("#94a3b8" if q["is_blank"] else "#dc2626")
                status_label = "✓ Correct" if q["is_correct"] else ("— Blank" if q["is_blank"] else "✗ Incorrect")
                table_rows.append([
                    Paragraph(str(q["global_num"]), cell_style),
                    Paragraph(escape(q["section_title"][:18]), cell_style),
                    Paragraph(escape(q["candidate_answer"][:30]), cell_style),
                    Paragraph(escape(q["correct_answer"][:30]), cell_style),
                    Paragraph(f'<font color="{status_color}"><b>{status_label}</b></font>', cell_style),
                ])
            q_table = Table(table_rows, colWidths=[25, 115, 150, 150, 60])
            q_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('PADDING', (0, 0), (-1, -1), 3),
            ]))
            story.append(q_table)

        story.append(Spacer(1, 15))
        story.append(Paragraph("<font size=7 color='#64748b'>Generated by IELTS Bhuiyan Online Examination System. Practice test report only; not an official IELTS Test Report Form.</font>", body_style))

        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
        doc.build(story)
        content_type = "application/pdf"

    filename = f"result_{attempt.candidate.username}_{module_type}_attempt_{attempt.pk}.{format}"
    response = HttpResponse(buffer.getvalue(), content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    return response


# ==============================================================================
# 2. COMPLETE ALL-MODULE FULL MOCK RESULT EXPORT
# ==============================================================================

@staff_member_required
@require_GET
def export_full_mock_attempt(request, full_attempt_id, format):
    if format not in ("pdf", "docx"):
        raise Http404("Unsupported export format.")

    full_mock = get_object_or_404(
        FullMockAttempt.objects.select_related(
            "candidate",
            "mock_test",
            "reading_attempt__module",
            "listening_attempt__module",
            "writing_attempt__module",
        ),
        pk=full_attempt_id,
    )
    if full_mock.status == FullMockAttempt.AttemptStatus.IN_PROGRESS:
        raise Http404("Active Full Mock exams cannot be exported until completed.")

    full_mock.calculate_overall_score()

    reading_data = get_module_attempt_data(full_mock.reading_attempt_id) if full_mock.reading_attempt_id else None
    listening_data = get_module_attempt_data(full_mock.listening_attempt_id) if full_mock.listening_attempt_id else None
    writing_data = get_module_attempt_data(full_mock.writing_attempt_id) if full_mock.writing_attempt_id else None

    buffer = BytesIO()

    if format == "docx":
        from docx import Document
        from docx.shared import Inches, Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT

        doc = Document()
        p_title = doc.add_heading("IELTS Full Mock Complete Exam Report", 0)
        p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Student & Exam Info
        p_sub = doc.add_paragraph()
        p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_sub.add_run(f"Candidate: {full_mock.candidate.get_full_name() or full_mock.candidate.username} ({full_mock.candidate.email})\n")
        p_sub.add_run(f"Test: {full_mock.mock_test.title} | Status: {full_mock.get_status_display()}\n")
        p_sub.add_run(f"Date: {format_local_dt(full_mock.started_at)}")

        doc.add_heading("Overall Exam Band Scores", level=1)
        score_table = doc.add_table(rows=5, cols=3)
        score_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        rows = [
            ("Module", "Raw Score", "Band Score"),
            ("Reading", f"{reading_data['raw_score']}/40" if reading_data else "—", f"Band {reading_data['band_score']}" if (reading_data and reading_data['band_score'] is not None) else "—"),
            ("Listening", f"{listening_data['raw_score']}/40" if listening_data else "—", f"Band {listening_data['band_score']}" if (listening_data and listening_data['band_score'] is not None) else "—"),
            ("Writing", "Manual Examiner Evaluation", f"Band {writing_data['writing_band']}" if (writing_data and writing_data['writing_band'] is not None) else "Pending Review"),
            ("OVERALL BAND SCORE", "—", f"Band {full_mock.overall_band_score}" if full_mock.overall_band_score is not None else "Pending Writing"),
        ]
        for r_idx, (c1, c2, c3) in enumerate(rows):
            cells = score_table.rows[r_idx].cells
            cells[0].paragraphs[0].add_run(c1).bold = (r_idx == 0 or r_idx == 4)
            cells[1].paragraphs[0].add_run(c2).bold = (r_idx == 0 or r_idx == 4)
            cells[2].paragraphs[0].add_run(c3).bold = (r_idx == 0 or r_idx == 4)

        doc.add_paragraph()

        # Writing Section Details
        if writing_data and writing_data["writing_tasks"]:
            doc.add_heading("Writing Tasks & Examiner Feedback", level=1)
            for t in writing_data["writing_tasks"]:
                doc.add_heading(f"Writing Task {t['task_number']}", level=2)
                p = doc.add_paragraph()
                p.add_run(f"Candidate Essay ({t['word_count']} words):\n").bold = True
                p.add_run(t["response"])
                ev = t["evaluation"]
                if ev:
                    p_ev = doc.add_paragraph()
                    p_ev.add_run(f"Scores: TA/TR: {ev.task_achievement} | CC: {ev.coherence_cohesion} | LR: {ev.lexical_resource} | GRA: {ev.grammatical_range_accuracy} | Task Average: {ev.criterion_average}\n").bold = True
                    p_ev.add_run(f"Examiner Feedback: {ev.feedback or '[No feedback recorded]'}")

        doc.add_paragraph("\nReport generated by IELTS Bhuiyan. Practice assessment only; not an official IELTS TRF.")
        doc.save(buffer)
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    else:
        # ReportLab PDF
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("FullTitle", parent=styles["Title"], fontSize=18, leading=22, textColor=colors.HexColor("#1e3a8a"))
        h1_style = ParagraphStyle("FullH1", parent=styles["Heading2"], fontSize=13, leading=16, textColor=colors.HexColor("#1e40af"), spaceBefore=10, spaceAfter=6)
        body_style = ParagraphStyle("FullBody", parent=styles["Normal"], fontSize=9, leading=12, textColor=colors.HexColor("#1f2937"))
        cell_style = ParagraphStyle("FullCell", parent=styles["Normal"], fontSize=8.5, leading=11)

        story = []
        story.append(Paragraph("IELTS Full Mock Complete Examination Report", title_style))
        story.append(Spacer(1, 8))

        # Header info
        info_rows = [
            [Paragraph("<b>Candidate:</b>", body_style), Paragraph(f"{full_mock.candidate.get_full_name() or full_mock.candidate.username} ({full_mock.candidate.email})", body_style)],
            [Paragraph("<b>Mock Test:</b>", body_style), Paragraph(full_mock.mock_test.title, body_style)],
            [Paragraph("<b>Date Started:</b>", body_style), Paragraph(format_local_dt(full_mock.started_at), body_style)],
            [Paragraph("<b>Overall Band:</b>", body_style), Paragraph(f"<b>Band {full_mock.overall_band_score}</b>" if full_mock.overall_band_score is not None else "Pending Writing Evaluation", body_style)],
        ]
        t_info = Table(info_rows, colWidths=[100, 400])
        t_info.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
            ('PADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(t_info)
        story.append(Spacer(1, 14))

        # Scores Summary Table
        story.append(Paragraph("<b>Module Score Breakdown</b>", h1_style))
        scores_data = [
            [Paragraph("<b>Module</b>", cell_style), Paragraph("<b>Raw Score</b>", cell_style), Paragraph("<b>Band Score</b>", cell_style)],
            [Paragraph("Reading", cell_style), Paragraph(f"{reading_data['raw_score']}/40" if reading_data else "—", cell_style), Paragraph(f"Band {reading_data['band_score']}" if (reading_data and reading_data['band_score'] is not None) else "—", cell_style)],
            [Paragraph("Listening", cell_style), Paragraph(f"{listening_data['raw_score']}/40" if listening_data else "—", cell_style), Paragraph(f"Band {listening_data['band_score']}" if (listening_data and listening_data['band_score'] is not None) else "—", cell_style)],
            [Paragraph("Writing", cell_style), Paragraph("Manual Assessment", cell_style), Paragraph(f"Band {writing_data['writing_band']}" if (writing_data and writing_data['writing_band'] is not None) else "Pending Review", cell_style)],
            [Paragraph("<b>OVERALL BAND SCORE</b>", cell_style), Paragraph("—", cell_style), Paragraph(f"<b>Band {full_mock.overall_band_score}</b>" if full_mock.overall_band_score is not None else "Pending Writing", cell_style)],
        ]
        t_scores = Table(scores_data, colWidths=[180, 160, 160])
        t_scores.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor("#dbeafe")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ('PADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(t_scores)
        story.append(Spacer(1, 14))

        # Writing Details
        if writing_data and writing_data["writing_tasks"]:
            story.append(Paragraph("<b>Writing Tasks & Examiner Feedback</b>", h1_style))
            for task in writing_data["writing_tasks"]:
                story.append(Paragraph(f"<b>Writing Task {task['task_number']}</b> ({task['word_count']} words)", body_style))
                story.append(Spacer(1, 3))
                resp_snippet = escape(task["response"][:350]) + ("..." if len(task["response"]) > 350 else "")
                story.append(Paragraph(f"<i>Candidate Response:</i> {resp_snippet}", cell_style))
                ev = task["evaluation"]
                if ev:
                    story.append(Spacer(1, 3))
                    story.append(Paragraph(f"<b>Scores:</b> TA: {ev.task_achievement} | CC: {ev.coherence_cohesion} | LR: {ev.lexical_resource} | GRA: {ev.grammatical_range_accuracy} &nbsp; <b>[Average: {ev.criterion_average}]</b>", cell_style))
                    if ev.feedback:
                        story.append(Paragraph(f"<b>Feedback:</b> {escape(ev.feedback)}", cell_style))
                story.append(Spacer(1, 8))

        story.append(Spacer(1, 15))
        story.append(Paragraph("<font size=7 color='#64748b'>Generated by IELTS Bhuiyan Online Examination System. Practice test report only; not an official IELTS Test Report Form.</font>", body_style))

        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
        doc.build(story)
        content_type = "application/pdf"

    filename = f"full_mock_{full_mock.candidate.username}_test_{full_mock.mock_test.test_number}_{full_mock.pk}.{format}"
    response = HttpResponse(buffer.getvalue(), content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    return response
