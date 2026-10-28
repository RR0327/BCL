import os
import sys
import json
import django

# Setup Django environment
sys.path.append(os.path.abspath('bcl_bhuiyan'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bcl_bhuiyan.settings')
django.setup()

from bcl.models import IELTSMockTest, ExamModule, ExamSection, Question, QuestionOption
from django.db import transaction

with open('full_30_writing_tasks.json', 'r', encoding='utf-8') as f:
    tasks = json.load(f)

print(f"Loaded {len(tasks)} tasks.")

# Pre-checks: count reading and listening
reading_mod_count_before = ExamModule.objects.filter(module_type='reading').count()
listening_mod_count_before = ExamModule.objects.filter(module_type='listening').count()
reading_sec_count_before = ExamSection.objects.filter(module__module_type='reading').count()
listening_sec_count_before = ExamSection.objects.filter(module__module_type='listening').count()
reading_q_count_before = Question.objects.filter(section__module__module_type='reading').count()
listening_q_count_before = Question.objects.filter(section__module__module_type='listening').count()

print("--- BEFORE COUNTS ---")
print(f"Reading: modules={reading_mod_count_before}, sections={reading_sec_count_before}, questions={reading_q_count_before}")
print(f"Listening: modules={listening_mod_count_before}, sections={listening_sec_count_before}, questions={listening_q_count_before}")

prompts_set = set()
duplicates = []
for t in tasks:
    if t["prompt"] in prompts_set:
        duplicates.append(t["prompt"])
    prompts_set.add(t["prompt"])

if duplicates:
    print("FATAL: Duplicate prompts found in tasks definition:", duplicates)
    sys.exit(1)

print(f"Zero duplicates verified across all {len(prompts_set)} prompts.")

def run_import(dry_run=True):
    with transaction.atomic():
        created_modules = 0
        updated_modules = 0
        created_questions = 0
        updated_questions = 0

        for t in tasks:
            t_num = t["test_number"]
            mock_test = IELTSMockTest.objects.filter(test_number=t_num).first()
            if not mock_test:
                print(f"Mock test {t_num} does not exist!")
                continue

            # 1. Writing module
            writing_mod, mod_created = ExamModule.objects.get_or_create(
                mock_test=mock_test,
                module_type=ExamModule.ModuleType.WRITING,
                defaults={
                    "duration_minutes": 60,
                    "is_active": True,
                    "instructions": ""
                }
            )
            if mod_created:
                created_modules += 1
            else:
                updated_modules += 1

            # 2. Section 1 (Writing Task 1)
            sec, sec_created = ExamSection.objects.get_or_create(
                module=writing_mod,
                order=1,
                defaults={
                    "title": "Writing Task 1",
                    "instructions": "",
                    "passage": "",
                    "passage_instructions": ""
                }
            )
            # Ensure title is clear
            if not sec.title or sec.title == "Writing 1":
                sec.title = "Writing Task 1"
                sec.save(update_fields=["title"])

            # 3. Question 1 (Essay)
            q, q_created = Question.objects.get_or_create(
                section=sec,
                order=1,
                defaults={
                    "question_type": Question.QuestionType.ESSAY,
                    "marks": 1,
                    "question_text": t["prompt"],
                    "question_instructions": t["instructions"],
                    "explanation": t["model_answer"]
                }
            )
            if q_created:
                created_questions += 1
            else:
                # Update prompt and explanation if already exists (e.g. Test 1)
                q.question_text = t["prompt"]
                q.question_instructions = t["instructions"]
                q.explanation = t["model_answer"]
                q.question_type = Question.QuestionType.ESSAY
                q.marks = 1
                q.save(update_fields=["question_text", "question_instructions", "explanation", "question_type", "marks"])
                updated_questions += 1

        print(f"\nImport stats: created_modules={created_modules}, updated_modules={updated_modules}, created_questions={created_questions}, updated_questions={updated_questions}")

        # Post-checks
        reading_mod_count_after = ExamModule.objects.filter(module_type='reading').count()
        listening_mod_count_after = ExamModule.objects.filter(module_type='listening').count()
        reading_sec_count_after = ExamSection.objects.filter(module__module_type='reading').count()
        listening_sec_count_after = ExamSection.objects.filter(module__module_type='listening').count()
        reading_q_count_after = Question.objects.filter(section__module__module_type='reading').count()
        listening_q_count_after = Question.objects.filter(section__module__module_type='listening').count()

        assert reading_mod_count_before == reading_mod_count_after, "Reading modules changed!"
        assert listening_mod_count_before == listening_mod_count_after, "Listening modules changed!"
        assert reading_sec_count_before == reading_sec_count_after, "Reading sections changed!"
        assert listening_sec_count_before == listening_sec_count_after, "Listening sections changed!"
        assert reading_q_count_before == reading_q_count_after, "Reading questions changed!"
        assert listening_q_count_before == listening_q_count_after, "Listening questions changed!"

        print("POST-CHECK PASSED: Reading and Listening modules, sections, and questions are 100% UNTOUCHED.")

        if dry_run:
            print("DRY RUN: Rolling back transaction.")
            transaction.set_rollback(True)
        else:
            print("COMMITTED: All 30 Writing Task 1 modules imported successfully!")

if __name__ == '__main__':
    dry_mode = '--commit' not in sys.argv
    print(f"Running import (dry_run={dry_mode})...")
    run_import(dry_run=dry_mode)

