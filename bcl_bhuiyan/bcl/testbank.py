"""Test-bank readiness checks and safe JSON content ingestion."""
import json
from pathlib import Path
from django.core.exceptions import ValidationError
from django.db import transaction
from .models import IELTSMockTest, ExamModule, ExamSection, Question, QuestionOption

MODULES = ('reading', 'listening', 'writing')
EXPECTED_SECTIONS = {'reading': 3, 'listening': 4, 'writing': 2}
EXPECTED_QUESTIONS = {'reading': 40, 'listening': 40, 'writing': 2}

QUESTION_TYPE_ALIASES = {
    # Fill in the blank variants
    "note_completion": "fill_blank",
    "notes_completion": "fill_blank",
    "summary_completion": "fill_blank",
    "table_completion": "fill_blank",
    "sentence_completion": "fill_blank",
    "flowchart_completion": "fill_blank",
    "flow_chart_completion": "fill_blank",
    "form_completion": "fill_blank",
    "fill_in_the_blank": "fill_blank",
    "fill_in_the_blanks": "fill_blank",
    "fill_blanks": "fill_blank",
    "blank": "fill_blank",

    # Matching variants
    "matching_headings": "matching",
    "matching_heading": "matching",
    "headings": "matching",
    "matching_features": "matching",
    "matching_names": "matching",
    "matching_sentence_endings": "matching",

    # True / False / Not Given
    "true_false_not_given": "tfng",
    "true_false": "tfng",

    # Yes / No / Not Given
    "yes_no_not_given": "ynng",
    "yes_no": "ynng",

    # Multiple Choice
    "multiple_choice": "mcq",
    "single_choice": "mcq",

    # Multi Select
    "multiple_select": "multi_select",
    "choose_two": "multi_select",
    "choose_three": "multi_select",

    # Map / Diagram
    "diagram_labelling": "map_labelling",
    "plan_labelling": "map_labelling",
    "map_labeling": "map_labelling",
    "diagram_labeling": "map_labelling",
}


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
            if kind == 'listening' and not (module.audio_file or section.audio_file):
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


def import_test(payload, *, publish=False, overwrite=False):
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
            if not overwrite and (test.is_published or test.modules.exists() or
                    test.modules.filter(attempts__isnull=False).exists()):
                raise ValidationError(f'Test {number} already contains content or is published; import will not overwrite it')
            if overwrite:
                from .models import CandidateAttempt
                CandidateAttempt.objects.filter(module__mock_test=test).delete()
                test.modules.all().delete()
                test.is_published = False
            test.title = title
            test.description = str(payload.get('description', ''))
            update_fields = ['title', 'description', 'updated_at']
            if overwrite:
                update_fields.append('is_published')
            test.save(update_fields=update_fields)
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
                    raw_qtype = str(qdata.get('question_type', '')).strip().lower()
                    qtype = QUESTION_TYPE_ALIASES.get(raw_qtype, raw_qtype)
                    if qtype not in Question.QuestionType.values:
                        raise ValidationError(f'Unsupported question type: {qtype}')
                    exp_val = qdata.get('explanation', '')
                    if isinstance(exp_val, dict):
                        passage_excerpt = str(qdata.get('passage_excerpt') or exp_val.get('passage_excerpt', ''))
                        answer_location = str(qdata.get('answer_location') or exp_val.get('answer_location', ''))
                        what_question_asks = str(qdata.get('what_question_asks') or exp_val.get('what_question_asks', ''))
                        what_passage_says = str(qdata.get('what_passage_says') or exp_val.get('what_passage_says', ''))
                        why_answer = str(qdata.get('why_answer') or exp_val.get('why_answer', ''))
                        paraphrase = str(qdata.get('paraphrase') or exp_val.get('paraphrase', ''))
                        tip = str(qdata.get('tip') or exp_val.get('tip', ''))
                        explanation = str(why_answer or exp_val.get('summary', ''))
                    else:
                        passage_excerpt = str(qdata.get('passage_excerpt', ''))
                        answer_location = str(qdata.get('answer_location', ''))
                        what_question_asks = str(qdata.get('what_question_asks', ''))
                        what_passage_says = str(qdata.get('what_passage_says', ''))
                        why_answer = str(qdata.get('why_answer', ''))
                        paraphrase = str(qdata.get('paraphrase', ''))
                        tip = str(qdata.get('tip', ''))
                        explanation = str(exp_val or why_answer)

                    q = Question.objects.create(
                        section=section,
                        order=question_index,
                        question_type=qtype,
                        question_text=str(qdata.get('question_text', '')),
                        question_instructions=str(qdata.get('question_instructions', '')),
                        answer_count=max(1, int(qdata.get('answer_count', 1))),
                        correct_answer=str(qdata.get('correct_answer', '')),
                        marks=int(qdata.get('marks', 1)),
                        explanation=explanation,
                        passage_excerpt=passage_excerpt,
                        answer_location=answer_location,
                        what_question_asks=what_question_asks,
                        what_passage_says=what_passage_says,
                        why_answer=why_answer,
                        paraphrase=paraphrase,
                        tip=tip,
                    )
                    for index, option in enumerate(qdata.get('options', []), 1):
                        opt_key = str(option.get('option_key') or option.get('key', ''))
                        opt_text = str(option.get('option_text') or option.get('text', ''))
                        QuestionOption.objects.create(question=q, order=index, option_key=opt_key, option_text=opt_text, is_correct=bool(option.get('is_correct', False)))
        if publish:
            issues = readiness(test)
            if issues:
                raise ValidationError('Cannot publish: ' + '; '.join(issues[:15]))
            test.is_published = True
            test.save(update_fields=['is_published'])
        return test
