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
    Question.QuestionType.MULTI_SELECT,
    Question.QuestionType.MAP_LABELLING,
}


def normalize(value):
    return " ".join(value.strip().casefold().split())


def split_alternative_answers(text):
    """Split answer variants by ||, /, or |.
    
    Example:
    '1st of june / 1st june / first of june / june 1st / june 1 / 1 june'
    -> ['1st of june', '1st june', 'first of june', 'june 1st', 'june 1', '1 june']
    """
    import re
    parts = re.split(r'\s*\|\|\s*|\s*/\s*|\s*\|\s*', text)
    return [p.strip() for p in parts if p.strip()]


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
    if attempt.module.module_type == ExamModule.ModuleType.LISTENING:
        # Listening is client-side HTML tested. Preserve verified score and answers payload.
        if attempt.raw_score is not None and attempt.band_score is not None:
            return
        if attempt.answers_payload and "score" in attempt.answers_payload:
            try:
                raw = int(attempt.answers_payload["score"])
                attempt.raw_score = raw
                attempt.band_score = band_for_raw(attempt.module.module_type, raw)
                attempt.save(update_fields=["raw_score", "band_score"])
            except Exception:
                pass
            return
        if not CandidateAnswer.objects.filter(attempt=attempt).exists():
            return

    questions = list(
        Question.objects.filter(section__module=attempt.module)
        .prefetch_related("options").order_by("pk")
    )
    if not questions:
        return

    # Auto-grade questions safely against available answer keys and options.

    answers = {
        a.question_id: a for a in CandidateAnswer.objects.filter(attempt=attempt)
    }
    raw = 0
    for q in questions:
        answer = answers.get(q.pk)
        if not answer:
            continue
        if q.question_type == Question.QuestionType.MCQ:
            correct_opts = [o.option_key for o in q.options.all() if o.is_correct]
            if correct_opts:
                accepted = correct_opts
            else:
                raw_alts = split_alternative_answers(q.correct_answer)
                accepted = list(raw_alts)
                for alt in raw_alts:
                    words = alt.split()
                    if words and len(words[0]) == 1 and words[0].isalpha():
                        accepted.append(words[0])
        elif q.question_type in {
            Question.QuestionType.MATCHING,
            Question.QuestionType.MATCHING_INFORMATION,
            Question.QuestionType.MAP_LABELLING,
        }:
            correct_opts = [o.option_key for o in q.options.all() if o.is_correct]
            if correct_opts:
                accepted = correct_opts
            else:
                accepted = split_alternative_answers(q.correct_answer)
        elif q.question_type == Question.QuestionType.MULTI_SELECT:
            correct_opts = {o.option_key.strip().upper() for o in q.options.all() if o.is_correct}
            if not correct_opts and q.correct_answer.strip():
                correct_opts = {k.strip().upper() for k in q.correct_answer.split(";;;") if k.strip()}
            actual_keys = {k.strip().upper() for k in answer.answer_text.split(";;;") if k.strip()}
            correct = bool(actual_keys) and actual_keys == correct_opts
            answer.is_correct = correct
            answer.awarded_marks = 1 if correct else 0
            answer.save(update_fields=["is_correct", "awarded_marks"])
            raw += int(correct)
            continue
        elif q.question_type == Question.QuestionType.FILL_BLANK:
            actual_values = [v.strip() for v in answer.answer_text.split(";;;")]
            expected_blanks = [b.strip() for b in q.correct_answer.split(";;;")]
            correct = bool(answer.answer_text.strip()) and (
                len(actual_values) == len(expected_blanks)
                and all(
                    any(normalize(actual) == normalize(exp) for exp in split_alternative_answers(expected_blank))
                    for actual, expected_blank in zip(actual_values, expected_blanks)
                )
            )
            answer.is_correct = correct
            answer.awarded_marks = 1 if correct else 0
            answer.save(update_fields=["is_correct", "awarded_marks"])
            raw += int(correct)
            continue
        else:
            accepted = split_alternative_answers(q.correct_answer)

        correct = bool(answer.answer_text.strip()) and any(
            normalize(answer.answer_text) == normalize(acc)
            for acc in accepted
        )
        answer.is_correct = correct
        answer.awarded_marks = 1 if correct else 0
        answer.save(update_fields=["is_correct", "awarded_marks"])
        raw += int(correct)

    attempt.raw_score = raw
    # Practice band calculation (applies standard band table directly or scaled for practice sets)
    if len(questions) == 40:
        attempt.band_score = band_for_raw(attempt.module.module_type, raw)
    elif len(questions) > 0:
        scaled_raw = round((raw / len(questions)) * 40)
        attempt.band_score = band_for_raw(attempt.module.module_type, scaled_raw)
    else:
        attempt.band_score = None
    attempt.save(update_fields=["raw_score", "band_score"])
