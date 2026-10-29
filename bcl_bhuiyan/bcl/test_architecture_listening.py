import os
import json
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from .models import (
    IELTSMockTest,
    ExamModule,
    ExamSection,
    Question,
    CandidateAttempt,
    FullMockAttempt,
)


class ArchitectureAndIntegrityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="candidate_arch_test",
            email="candidate_arch@example.com",
            first_name="Jane",
            last_name="Doe",
            password="TestPassword123!",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_listening_html_files_exist_1_to_30(self):
        """Verify all 30 serial listening mock HTML files exist on disk."""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        listening_dir = os.path.join(base_dir, "listening")
        self.assertTrue(os.path.isdir(listening_dir), f"Directory {listening_dir} must exist")

        for num in range(1, 31):
            filepath = os.path.join(listening_dir, f"listening-mock-{num}.html")
            self.assertTrue(
                os.path.isfile(filepath),
                f"File listening-mock-{num}.html must exist at {filepath}"
            )

    def test_listening_html_rendered_with_website_design_and_modal(self):
        """Verify the listening module serves raw HTML with unified website header and popup modal."""
        mock_test = IELTSMockTest.objects.create(
            test_number=1,
            title="Cambridge IELTS 1 Test 1",
            is_published=True,
        )
        listening_mod = ExamModule.objects.create(
            mock_test=mock_test,
            module_type=ExamModule.ModuleType.LISTENING,
            duration_minutes=30,
            is_active=True,
        )

        res = self.client.get(reverse("bcl:mock_listening", args=[mock_test.pk]))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8", errors="replace")

        # Must have website header
        self.assertIn("bcl-exam-header", content)
        self.assertIn("Test 1: Cambridge IELTS 1 Test 1", content)
        self.assertIn("Dashboard", content)

        # Must have 35:00 timer and Geist fonts
        self.assertIn("35:00", content)
        self.assertIn("Geist", content)
        self.assertIn("Geist Mono", content)
        self.assertIn("bclTimerInterval", content)

        # Must have modern modal popup
        self.assertIn("bcl-listening-modal", content)
        self.assertIn("Exam Result &amp; Answers Review", content)

        # Must have student answers extraction & bridge
        self.assertIn("extractAnswersAndScore", content)
        self.assertIn("answers_payload", content)

    def test_listening_submission_stores_score_and_answers_payload(self):
        """Verify student score and answers payload are persisted to CandidateAttempt in database."""
        mock_test = IELTSMockTest.objects.create(
            test_number=1,
            title="Mock Test 1 Storage Test",
            is_published=True,
        )
        listening_mod = ExamModule.objects.create(
            mock_test=mock_test,
            module_type=ExamModule.ModuleType.LISTENING,
            duration_minutes=30,
            is_active=True,
        )

        # Start listening attempt
        self.client.get(reverse("bcl:mock_listening", args=[mock_test.pk]))
        attempt = CandidateAttempt.objects.get(candidate=self.user, module=listening_mod)

        # Mock answers payload collected from student
        sample_answers = {
            "score": 36,
            "total": 40,
            "band_score": "8.0",
            "answers": {
                "1": {"user_answer": "SILENT", "correct_answer": "SILENT", "is_correct": True},
                "2": {"user_answer": "RUDE", "correct_answer": "RUDE", "is_correct": True},
                "3": {"user_answer": "OFTEN", "correct_answer": "RARELY", "is_correct": False},
                "4": {"user_answer": "SMOKE", "correct_answer": "SMOKE", "is_correct": True},
            }
        }

        # Submit listening test via AJAX
        res_sub = self.client.post(
            reverse("bcl:mock_listening_submit", args=[mock_test.pk]),
            {
                "raw_score": 36,
                "band_score": "8.0",
                "module_type": "listening",
                "answers_payload": json.dumps(sample_answers),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_sub.status_code, 200)

        # Verify DB persistence
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, CandidateAttempt.AttemptStatus.SUBMITTED)
        self.assertEqual(attempt.raw_score, 36)
        self.assertEqual(attempt.band_score, Decimal("8.0"))
        self.assertIsNotNone(attempt.submitted_at)

        # Verify answers payload stored in DB
        self.assertIn("answers", attempt.answers_payload)
        self.assertEqual(attempt.answers_payload["answers"]["1"]["user_answer"], "SILENT")
        self.assertEqual(attempt.answers_payload["answers"]["3"]["is_correct"], False)

    def test_sequential_full_mock_flow_and_sequence_guard(self):
        """
        Verify Mode B Sequential Full Mock Test:
        /start-mock/ -> /mock/<id>/listening/ -> /mock/<id>/reading/ -> /mock/<id>/writing/ -> /mock/<id>/consolidated-result/
        Also verify Server-Side Sequence Guard prevents bypassing.
        """
        mock_test = IELTSMockTest.objects.create(
            test_number=2,
            title="Mock Test 2 Architecture Test",
            is_published=True,
        )
        listening_mod = ExamModule.objects.create(
            mock_test=mock_test,
            module_type=ExamModule.ModuleType.LISTENING,
            duration_minutes=30,
            is_active=True,
        )
        reading_mod = ExamModule.objects.create(
            mock_test=mock_test,
            module_type=ExamModule.ModuleType.READING,
            duration_minutes=60,
            is_active=True,
        )
        writing_mod = ExamModule.objects.create(
            mock_test=mock_test,
            module_type=ExamModule.ModuleType.WRITING,
            duration_minutes=60,
            is_active=True,
        )

        sec_r = ExamSection.objects.create(module=reading_mod, order=1, title="Section 1")
        Question.objects.create(section=sec_r, order=1, question_type=Question.QuestionType.MCQ, question_text="Q1", correct_answer="A")

        sec_w = ExamSection.objects.create(module=writing_mod, order=1, title="Task 1")
        Question.objects.create(section=sec_w, order=1, question_type=Question.QuestionType.ESSAY, question_text="Task 1 prompt")

        # 1. Sequence Guard Test: Cannot directly access reading before starting
        res_guard_reading = self.client.get(reverse("bcl:mock_reading", args=[mock_test.pk]))
        self.assertEqual(res_guard_reading.status_code, 302)
        self.assertIn(reverse("bcl:mock_listening", args=[mock_test.pk]), res_guard_reading.url)

        # 2. Sequence Guard Test: Cannot directly access writing before starting
        res_guard_writing = self.client.get(reverse("bcl:mock_writing", args=[mock_test.pk]))
        self.assertEqual(res_guard_writing.status_code, 302)
        self.assertIn(reverse("bcl:mock_listening", args=[mock_test.pk]), res_guard_writing.url)

        # 3. Mode B: POST /start-mock/
        res_start = self.client.post(reverse("bcl:start_mock_shortcut"), {"mock_id": mock_test.pk})
        self.assertEqual(res_start.status_code, 302)
        self.assertIn(reverse("bcl:mock_listening", args=[mock_test.pk]), res_start.url)

        # 4. Mode B: GET /mock/<id>/listening/ renders raw HTML + bridge
        res_listening = self.client.get(reverse("bcl:mock_listening", args=[mock_test.pk]))
        self.assertEqual(res_listening.status_code, 200)

        # Verify FullMockAttempt was created with current_step='listening'
        full_mock = FullMockAttempt.objects.get(candidate=self.user, mock_test=mock_test)
        self.assertEqual(full_mock.current_step, "listening")
        self.assertIsNotNone(full_mock.listening_attempt)

        # Sequence Guard Test: Still cannot access reading while listening is in progress
        res_guard_reading2 = self.client.get(reverse("bcl:mock_reading", args=[mock_test.pk]))
        self.assertEqual(res_guard_reading2.status_code, 302)
        self.assertIn(reverse("bcl:mock_listening", args=[mock_test.pk]), res_guard_reading2.url)

        # 5. Mode B: POST /mock/<id>/listening/submit/ with raw_score=36 and answers
        payload = {
            "score": 36,
            "total": 40,
            "answers": {
                "1": {"user_answer": "SILENT", "correct_answer": "SILENT", "is_correct": True}
            }
        }
        res_listen_sub = self.client.post(
            reverse("bcl:mock_listening_submit", args=[mock_test.pk]),
            {
                "raw_score": 36,
                "band_score": "8.0",
                "module_type": "listening",
                "answers_payload": json.dumps(payload),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_listen_sub.status_code, 200)
        json_data = res_listen_sub.json()
        self.assertEqual(json_data["status"], "ok")
        self.assertEqual(json_data["raw_score"], 36)

        # Verify step advanced to 'reading' and payload stored
        full_mock.refresh_from_db()
        self.assertEqual(full_mock.current_step, "reading")
        self.assertEqual(full_mock.listening_attempt.status, CandidateAttempt.AttemptStatus.SUBMITTED)
        self.assertEqual(full_mock.listening_attempt.raw_score, 36)
        self.assertIn("answers", full_mock.listening_attempt.answers_payload)

        # 6. Mode B: GET /mock/<id>/reading/ now allowed and redirects to session
        res_reading = self.client.get(reverse("bcl:mock_reading", args=[mock_test.pk]))
        self.assertEqual(res_reading.status_code, 302)
        full_mock.refresh_from_db()
        self.assertIsNotNone(full_mock.reading_attempt)
        self.assertIn(f"/exam/session/{full_mock.reading_attempt.pk}/", res_reading.url)

        # Sequence Guard Test: Still cannot access writing while reading is in progress
        res_guard_writing2 = self.client.get(reverse("bcl:mock_writing", args=[mock_test.pk]))
        self.assertEqual(res_guard_writing2.status_code, 302)
        self.assertIn(reverse("bcl:mock_reading", args=[mock_test.pk]), res_guard_writing2.url)

        # 7. Mode B: POST /mock/<id>/reading/submit/
        res_read_sub = self.client.post(
            reverse("bcl:mock_reading_submit", args=[mock_test.pk]),
            {f"q_{Question.objects.filter(section__module=reading_mod).first().pk}": "A"},
        )
        self.assertEqual(res_read_sub.status_code, 302)

        full_mock.refresh_from_db()
        self.assertEqual(full_mock.current_step, "writing")
        self.assertEqual(full_mock.reading_attempt.status, CandidateAttempt.AttemptStatus.SUBMITTED)

        # 8. Mode B: GET /mock/<id>/writing/ now allowed
        res_writing = self.client.get(reverse("bcl:mock_writing", args=[mock_test.pk]))
        self.assertEqual(res_writing.status_code, 302)
        full_mock.refresh_from_db()
        self.assertIsNotNone(full_mock.writing_attempt)
        self.assertIn(f"/exam/session/{full_mock.writing_attempt.pk}/", res_writing.url)

        # 9. Mode B: POST /mock/<id>/writing/submit/
        task_q = Question.objects.filter(section__module=writing_mod).first()
        res_write_sub = self.client.post(
            reverse("bcl:mock_writing_submit", args=[mock_test.pk]),
            {f"q_{task_q.pk}": "Sample writing response for task 1."},
        )
        self.assertEqual(res_write_sub.status_code, 302)

        full_mock.refresh_from_db()
        self.assertEqual(full_mock.current_step, "completed")
        self.assertEqual(full_mock.status, FullMockAttempt.AttemptStatus.SUBMITTED)

        # 10. Mode B: GET /mock/<id>/consolidated-result/
        res_consolidated = self.client.get(reverse("bcl:mock_consolidated_result", args=[mock_test.pk]))
        self.assertEqual(res_consolidated.status_code, 302)
        self.assertIn(reverse("bcl:full_mock_result", args=[full_mock.pk]), res_consolidated.url)

    def test_dashboard_displays_35_min_and_allows_resume(self):
        """Verify dashboard displays 35 min for listening, 155 min for full mock, and allows resume."""
        mock_test = IELTSMockTest.objects.create(
            test_number=3,
            title="Mock Test 3 Dashboard Test",
            is_published=True,
        )
        listening_mod = ExamModule.objects.create(
            mock_test=mock_test,
            module_type=ExamModule.ModuleType.LISTENING,
            duration_minutes=35,
            is_active=True,
        )
        reading_mod = ExamModule.objects.create(
            mock_test=mock_test,
            module_type=ExamModule.ModuleType.READING,
            duration_minutes=60,
            is_active=True,
        )
        writing_mod = ExamModule.objects.create(
            mock_test=mock_test,
            module_type=ExamModule.ModuleType.WRITING,
            duration_minutes=60,
            is_active=True,
        )

        res = self.client.get(reverse("bcl:dashboard"))
        self.assertEqual(res.status_code, 200)
        dash_content = res.content.decode("utf-8")
        self.assertIn("35 min", dash_content)
        self.assertIn("155 min", dash_content)

        # Start a listening attempt to verify in-progress resume link
        self.client.get(reverse("bcl:mock_listening", args=[mock_test.pk]))
        res2 = self.client.get(reverse("bcl:dashboard"))
        self.assertEqual(res2.status_code, 200)
        dash_content2 = res2.content.decode("utf-8")
        self.assertIn("In Progress", dash_content2)
        # Should NOT contain the disabled button
        self.assertNotIn("Listening examinations cannot be resumed", dash_content2)
        # Should contain active resume link to mock_listening
        self.assertIn(reverse("bcl:mock_listening", args=[mock_test.pk]), dash_content2)

    def test_mock_1_and_30_continuous_audio_engine(self):
        """Verify Mock 1 and Mock 30 render with continuous audio engine and complete base64 audio."""
        for test_num in [1, 30]:
            mock_test, _ = IELTSMockTest.objects.get_or_create(
                test_number=test_num,
                defaults={"title": f"Cambridge IELTS Mock Test {test_num}", "is_published": True}
            )
            ExamModule.objects.get_or_create(
                mock_test=mock_test,
                module_type=ExamModule.ModuleType.LISTENING,
                defaults={"duration_minutes": 35, "is_active": True}
            )

            res = self.client.get(reverse("bcl:mock_listening", args=[mock_test.pk]))
            self.assertEqual(res.status_code, 200)
            content = res.content.decode("utf-8", errors="replace")

            # Check continuous audio engine script and rules
            self.assertIn("lockAudioContinuous", content)
            self.assertIn("bcl_listening_audio_", content)
            self.assertIn("window.__bclAllowSubmissionPause", content)
            self.assertIn("showAutoplayResumePill", content)
            self.assertIn("audio-wave-bars playing", content)
            self.assertIn("Listening Audio in Progress", content)
            self.assertIn("IELTS Listening audio cannot be paused during the examination.", content)

            # Check website styling and Geist fonts
            self.assertIn("family=Geist:wght@400;500;600;700;800&family=Geist+Mono", content)
            self.assertIn("--font-sans: 'Geist'", content)
            self.assertIn("#bcl-exam-header", content)
            self.assertIn("bcl-submit-btn", content)
            self.assertIn("bcl-modal-container", content)

    def test_reading_and_writing_untouched_and_unharmed(self):
        """Verify Reading (30 modules, 90 sections, 1193 questions) and Writing (30 modules, 30 sections, 60 questions) remain 100% intact in db.sqlite3."""
        import sqlite3
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(base_dir, "db.sqlite3")
        self.assertTrue(os.path.exists(db_path), f"Database {db_path} must exist")

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        cur.execute("SELECT count(*) FROM bcl_exammodule WHERE module_type='reading'")
        r_mods = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM bcl_exammodule WHERE module_type='writing'")
        w_mods = cur.fetchone()[0]

        cur.execute("""
            SELECT count(*) FROM bcl_examsection s 
            JOIN bcl_exammodule m ON s.module_id = m.id 
            WHERE m.module_type = 'reading'
        """)
        r_secs = cur.fetchone()[0]

        cur.execute("""
            SELECT count(*) FROM bcl_examsection s 
            JOIN bcl_exammodule m ON s.module_id = m.id 
            WHERE m.module_type = 'writing'
        """)
        w_secs = cur.fetchone()[0]

        cur.execute("""
            SELECT count(*) FROM bcl_question q
            JOIN bcl_examsection s ON q.section_id = s.id
            JOIN bcl_exammodule m ON s.module_id = m.id
            WHERE m.module_type = 'reading'
        """)
        r_ques = cur.fetchone()[0]

        cur.execute("""
            SELECT count(*) FROM bcl_question q
            JOIN bcl_examsection s ON q.section_id = s.id
            JOIN bcl_exammodule m ON s.module_id = m.id
            WHERE m.module_type = 'writing'
        """)
        w_ques = cur.fetchone()[0]
        conn.close()

        self.assertEqual(r_mods, 30)
        self.assertEqual(w_mods, 30)
        self.assertEqual(r_secs, 90)
        self.assertEqual(w_secs, 30)
        self.assertEqual(r_ques, 1193)
        self.assertEqual(w_ques, 60)

    def test_listening_instructions_and_tab_switch_violation_monitoring(self):
        """Verify initial entry instruction modal and tab switching violation warnings & auto-submit."""
        mock_test = IELTSMockTest.objects.create(
            test_number=4,
            title="Mock Test 4 Security & Instructions Test",
            is_published=True,
        )
        listening_mod = ExamModule.objects.create(
            mock_test=mock_test,
            module_type=ExamModule.ModuleType.LISTENING,
            duration_minutes=35,
            is_active=True,
        )

        # 1. Render listening module
        res = self.client.get(reverse("bcl:mock_listening", args=[mock_test.pk]))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8", errors="replace")

        # Must have initial instruction modal with exam rules
        self.assertIn("bcl-instruction-modal", content)
        self.assertIn("IELTS Academic Listening Instructions", content)
        self.assertIn("Continuous Audio Recording", content)
        self.assertIn("Exam Integrity &amp; Anti-Cheat Policy", content)
        self.assertIn("bclStartExamBtn", content)
        self.assertIn("bclDismissInstructions", content)
        self.assertIn("bclShowInstructions", content)
        self.assertIn("ℹ️ Instructions", content)

        # Must have violation modal and tab-switching event listeners
        self.assertIn("bcl-violation-modal", content)
        self.assertIn("bclViolationTitle", content)
        self.assertIn("bclViolationMessage", content)
        self.assertIn("bclAcknowledgeViolation", content)
        self.assertIn("visibilitychange", content)
        self.assertIn("tab_hidden", content)
        self.assertIn("reportViolation", content)

        attempt = CandidateAttempt.objects.get(candidate=self.user, module=listening_mod)
        self.assertEqual(attempt.violation_count, 0)
        self.assertEqual(attempt.status, CandidateAttempt.AttemptStatus.IN_PROGRESS)

        # 2. First tab switch violation
        res_v1 = self.client.post(
            reverse("bcl:report_exam_violation", args=[attempt.pk]),
            json.dumps({"reason": "tab_hidden"}),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_v1.status_code, 200)
        data_v1 = res_v1.json()
        self.assertTrue(data_v1["warning"])
        self.assertFalse(data_v1["auto_submitted"])
        self.assertEqual(data_v1["violation_count"], 1)
        self.assertIn("First warning", data_v1["warning_message"])

        attempt.refresh_from_db()
        self.assertEqual(attempt.violation_count, 1)
        self.assertEqual(attempt.status, CandidateAttempt.AttemptStatus.IN_PROGRESS)

        # 3. Second tab switch violation
        res_v2 = self.client.post(
            reverse("bcl:report_exam_violation", args=[attempt.pk]),
            json.dumps({"reason": "window_blur"}),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_v2.status_code, 200)
        data_v2 = res_v2.json()
        self.assertTrue(data_v2["warning"])
        self.assertFalse(data_v2["auto_submitted"])
        self.assertEqual(data_v2["violation_count"], 2)
        self.assertIn("Final warning", data_v2["warning_message"])

        attempt.refresh_from_db()
        self.assertEqual(attempt.violation_count, 2)
        self.assertEqual(attempt.status, CandidateAttempt.AttemptStatus.IN_PROGRESS)

        # 4. Third tab switch violation -> AUTO-SUBMISSION triggered!
        answers_payload = {
            "score": 28,
            "total": 40,
            "band_score": "6.5",
            "answers": {"1": {"user_answer": "PARK", "correct_answer": "PARK", "is_correct": True}}
        }
        res_v3 = self.client.post(
            reverse("bcl:report_exam_violation", args=[attempt.pk]),
            json.dumps({
                "reason": "tab_hidden",
                "raw_score": 28,
                "answers_payload": answers_payload,
            }),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_v3.status_code, 200)
        data_v3 = res_v3.json()
        self.assertFalse(data_v3["warning"])
        self.assertTrue(data_v3["auto_submitted"])
        self.assertEqual(data_v3["violation_count"], 3)
        self.assertIn("redirect_url", data_v3)

        attempt.refresh_from_db()
        self.assertEqual(attempt.violation_count, 3)
        self.assertEqual(attempt.status, CandidateAttempt.AttemptStatus.AUTO_SUBMITTED)
        self.assertEqual(attempt.raw_score, 28)
        self.assertEqual(attempt.band_score, Decimal("6.5"))
        self.assertIn("answers", attempt.answers_payload)


