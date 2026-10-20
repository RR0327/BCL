"""Reading/Listening auto-marking. No AI Writing marking.

Band boundaries are configurable illustrative practice conversion tables,
not an official IELTS conversion guarantee. Apply only to complete 40-mark
modules. Adjust after agreeing a marking scheme with the client.
"""
from decimal import Decimal
from .models import CandidateAnswer, ExamModule, Question

# Inclusive minimum raw mark and associated practice band.
# These are illustrative, NOT definitive official IELTS tables.
PRACTICE_BAND_THRESHOLDS = {
    "reading": [
        (39, "9.0"), (37, "8.5"), (35, "8.0"), (33, "7.5"),
        (30, "7.0"), (27, "6.5"), (23, "6.0"), (19, "5.5"),
        (15, "5.0"), (13, "4.5"), (10, "4.0"), (8, "3.5"),
        (6, "3.0"), (4, "2.5"), (3, "2.0"), (2, "1.5"),
        (1, "1.0"), (0, "0.0"),
    ],
    "listening": [
        (39, "9.0"), (37, "8.5"), (35, "8.0"), (32, "7.5"),
        (30, "7.0"), (26, "6.5"), (23, "6.0"), (18, "5.5"),
        (16, "5.0"), (13, "4.5"), (11, "4.0"), (8, "3.5"),
        (6, "3.0"), (4, "2.5"), (3, "2.0"), (2, "1.5"),
        (1, "1.0"), (0, "0.0"),
    ],
}

SUPPORTED_TYPES = {
    Question.QuestionType.MCQ,
    Question.QuestionType.TRUE_FALSE_NOT_GIVEN,
    Question.QuestionType.YES_NO_NOT_GIVEN,
    Question.QuestionType.FILL_BLANK,
    Question.QuestionType.SHORT_ANSWER,
    Question.QuestionType.MATCHING,
    Question.QuestionType.MATCHING_INFORMATION,
}


def normalize(value):
    return " ".join(value.strip().casefold().split())


def band_for_raw(module_type, raw):
    for threshold, band in PRACTICE_BAND_THRESHOLDS[module_type]:
        if raw >= threshold:
            return Decimal(band)
    return None


def finalize_attempt_score(attempt):
    """Call while attempt row is locked, after final submission.

    Idempotent. Does not expose correct answers to the candidate. If any
    question is not safely auto-markable, leave total pending rather than
    presenting a misleading partial result.
    """
    if attempt.status == attempt.AttemptStatus.IN_PROGRESS:
        return
    if attempt.module.module_type == ExamModule.ModuleType.WRITING:
        return

    questions = list(
        Question.objects.filter(section__module=attempt.module)
        .prefetch_related("options").order_by("pk")
    )
    if not questions:
        return

    # Refuse to compute total with incomplete answer keys or formats.
    for q in questions:
        if q.question_type not in SUPPORTED_TYPES or q.marks != 1:
            return
        if q.question_type == Question.QuestionType.MCQ:
            options = list(q.options.all())
            correct_options = [o.option_key for o in options if o.is_correct]
            if len(correct_options) != 1:
                return
            # Two sources must agree when the canonical answer is supplied.
            if q.correct_answer.strip() and normalize(q.correct_answer) != normalize(correct_options[0]):
                return
        elif q.question_type in {
            Question.QuestionType.MATCHING,
            Question.QuestionType.MATCHING_INFORMATION,
        } and not (
            q.correct_answer.strip() or any(o.is_correct for o in q.options.all())
        ):
            return
        elif not q.correct_answer.strip():
            return

    answers = {
        a.question_id: a for a in CandidateAnswer.objects.filter(attempt=attempt)
    }
    raw = 0
    for q in questions:
        answer = answers.get(q.pk)
        if not answer:
            continue
        if q.question_type == Question.QuestionType.MCQ:
            expected = next(o.option_key for o in q.options.all() if o.is_correct)
            accepted = [expected]
        elif q.question_type in {
            Question.QuestionType.MATCHING,
            Question.QuestionType.MATCHING_INFORMATION,
        } and any(o.is_correct for o in q.options.all()):
            accepted = [o.option_key for o in q.options.all() if o.is_correct]
        else:
            # Alternative approved text answers can be separated by ||.
            accepted = [v for v in q.correct_answer.split("||") if v.strip()]
        actual_values = answer.answer_text.split(";;;") if q.question_type == Question.QuestionType.FILL_BLANK else [answer.answer_text]
        expected_values = q.correct_answer.split(";;;") if q.question_type == Question.QuestionType.FILL_BLANK else accepted
        correct = bool(answer.answer_text.strip()) and (
            len(actual_values) == len(expected_values)
            and all(
                any(normalize(actual) == normalize(expected) for expected in expected_value.split("||"))
                for actual, expected_value in zip(actual_values, expected_values)
            )
        )
        answer.is_correct = correct
        answer.awarded_marks = 1 if correct else 0
        answer.save(update_fields=["is_correct", "awarded_marks"])
        raw += int(correct)

    attempt.raw_score = raw
    # The practice conversion applies only to 40 one-mark questions.
    attempt.band_score = (
        band_for_raw(attempt.module.module_type, raw)
        if len(questions) == 40 else None
    )
    attempt.save(update_fields=["raw_score", "band_score"])
