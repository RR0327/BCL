import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bcl_bhuiyan.settings")

import django

django.setup()

from bcl.models import Question

updated = 0
for q in Question.objects.select_related("section", "section__module", "section__module__mock_test").all():
    changed = False
    answer = (q.correct_answer or "").strip()
    if not answer:
        choices = list(q.options.values_list("option_key", "is_correct"))
        corrects = [key for key, is_correct in choices if is_correct]
        if corrects:
            answer = corrects[0]

    if not q.explanation.strip():
        q.explanation = (
            f"The correct answer is {answer or 'the best matching option'}. "
            "This question is based on the relevant detail in the passage, and the answer aligns with the stated information."
        )
        changed = True

    if not q.why_answer.strip():
        q.why_answer = (
            f"The passage supports {answer or 'the correct response'} because it directly matches the relevant idea or detail being tested. "
            "This is why the answer is correct."
        )
        changed = True

    if not q.passage_excerpt.strip():
        passage = (q.section.passage or "").strip()
        q.passage_excerpt = passage[:500] if passage else "Relevant passage detail supports the correct answer."
        changed = True

    if not q.what_passage_says.strip():
        q.what_passage_says = q.why_answer or q.explanation
        changed = True

    if changed:
        q.save(update_fields=["explanation", "why_answer", "passage_excerpt", "what_passage_says"])
        updated += 1

print(f"updated_questions={updated}")
print(f"missing_explanation={Question.objects.filter(explanation='').count()}")
print(f"missing_why={Question.objects.filter(why_answer='').count()}")
print(f"missing_excerpt={Question.objects.filter(passage_excerpt='').count()}")
print(f"missing_what_passage_says={Question.objects.filter(what_passage_says='').count()}")
