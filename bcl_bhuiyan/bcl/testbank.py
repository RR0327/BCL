"""Test-bank readiness checks and safe JSON content ingestion."""
import json
from pathlib import Path
from django.core.exceptions import ValidationError
from django.db import transaction
from .models import IELTSMockTest, ExamModule, ExamSection, Question, QuestionOption

MODULES = ('reading', 'listening', 'writing')
EXPECTED_SECTIONS = {'reading': 3, 'listening': 4, 'writing': 2}
EXPECTED_QUESTIONS = {'reading': 40, 'listening': 40, 'writing': 2}


def readiness(test):
    """Return actionable problems; never equate placeholder content with a ready exam."""
    problems = []
    modules = {m.module_type: m for m in test.modules.prefetch_related('sections__questions__options')}
    for kind in MODULES:
        module = modules.get(kind)
        if not module:
            problems.append(f'{kind}: module missing')
            continue
        if not module.is_active:
            problems.append(f'{kind}: module inactive')
        sections = list(module.sections.all())
        if len(sections) != EXPECTED_SECTIONS[kind]:
            problems.append(f'{kind}: expected {EXPECTED_SECTIONS[kind]} sections, found {len(sections)}')
        count = sum(len(s.questions.all()) for s in sections)
        if count != EXPECTED_QUESTIONS[kind]:
            problems.append(f'{kind}: expected {EXPECTED_QUESTIONS[kind]} questions, found {count}')
        for section in sections:
            if kind == 'reading' and not section.passage.strip():
                problems.append(f'{kind} section {section.order}: passage missing')
            if kind == 'listening' and not section.audio_file:
                problems.append(f'{kind} section {section.order}: audio missing')
            if kind == 'writing' and not section.questions.all():
                problems.append(f'writing section {section.order}: essay prompt missing')
            for q in section.questions.all():
                if not q.question_text.strip():
                    problems.append(f'{kind} section {section.order} question {q.order}: prompt missing')
                if kind == 'writing':
                    if q.question_type != 'essay':
                        problems.append(f'writing question {q.order}: expected essay')
                else:
                    if q.question_type == 'essay':
                        problems.append(f'{kind} question {q.order}: unsupported auto-scoring type')
                    elif not q.correct_answer.strip() and not any(o.is_correct for o in q.options.all()):
                        problems.append(f'{kind} question {q.order}: answer key missing')
                    if q.question_type == 'mcq' and sum(o.is_correct for o in q.options.all()) != 1:
                        problems.append(f'{kind} question {q.order}: MCQ requires one correct option')
                    if q.question_type in ('matching', 'matching_information') and not any(o.is_correct for o in q.options.all()):
                        problems.append(f'{kind} question {q.order}: matching requires one correct option')
    return problems


def import_test(payload, *, publish=False):
    """Create a new test atomically. Never overwrite live content or candidate attempts."""
    if not isinstance(payload, dict) or not isinstance(payload.get('modules'), list):
        raise ValidationError('Expected object with modules array')
    try:
        number = int(payload['test_number'])
        title = str(payload['title']).strip()
    except (KeyError, ValueError, TypeError):
        raise ValidationError('test_number and title are required')
    if not 1 <= number <= 30 or not title:
        raise ValidationError('Test number must be 1–30 and title cannot be empty')
    if any(not isinstance(m, dict) for m in payload['modules']):
        raise ValidationError('Every module must be an object')
    kinds = [m.get('module_type') for m in payload['modules']]
    if len(kinds) != len(set(kinds)) or any(k not in MODULES for k in kinds):
        raise ValidationError('Module types must be unique and supported')
    with transaction.atomic():
        # Lock the numbered slot to prevent concurrent imports. Existing populated or
        # published slots must never be modified by the content importer.
        test = IELTSMockTest.objects.select_for_update().filter(test_number=number).first()
        if test is not None:
            if (test.is_published or test.modules.exists() or
                    test.modules.filter(attempts__isnull=False).exists()):
                raise ValidationError(f'Test {number} already contains content or is published; import will not overwrite it')
            test.title = title
            test.description = str(payload.get('description', ''))
            test.save(update_fields=['title', 'description', 'updated_at'])
        else:
            test = IELTSMockTest.objects.create(
                test_number=number, title=title,
                description=str(payload.get('description', '')), is_published=False,
            )
        for module_data in payload['modules']:
            kind = module_data['module_type']
            module = ExamModule.objects.create(mock_test=test, module_type=kind, duration_minutes=int(module_data.get('duration_minutes', 60)), instructions=str(module_data.get('instructions', '')))
            for section_index, section_data in enumerate(module_data.get('sections', []), 1):
                section = ExamSection.objects.create(module=module, order=section_index, title=str(section_data.get('title', f'Section {section_index}')), instructions=str(section_data.get('instructions', '')), passage_instructions=str(section_data.get('passage_instructions', '')), passage=str(section_data.get('passage', '')))
                # Audio/image files are uploaded separately through admin; never trust local paths from JSON.
                for question_index, qdata in enumerate(section_data.get('questions', []), 1):
                    qtype = qdata.get('question_type')
                    if qtype not in Question.QuestionType.values:
                        raise ValidationError(f'Unsupported question type: {qtype}')
                    q = Question.objects.create(section=section, order=question_index, question_type=qtype, question_text=str(qdata.get('question_text', '')), question_instructions=str(qdata.get('question_instructions', '')), answer_count=max(1, int(qdata.get('answer_count', 1))), correct_answer=str(qdata.get('correct_answer', '')), marks=int(qdata.get('marks', 1)), explanation=str(qdata.get('explanation', '')))
                    for index, option in enumerate(qdata.get('options', []), 1):
                        QuestionOption.objects.create(question=q, order=index, option_key=str(option['option_key']), option_text=str(option.get('option_text', '')), is_correct=bool(option.get('is_correct', False)))
        if publish:
            issues = readiness(test)
            if issues:
                raise ValidationError('Cannot publish: ' + '; '.join(issues[:15]))
            test.is_published = True
            test.save(update_fields=['is_published'])
        return test
