# Phase 5 Step 1 — Test bank ingestion and validation

The client must supply authorized passages, questions, images and audio. This step does not invent or distribute IELTS test material. The 30 slots are unpublished placeholders, not completed tests.

## Commands

From `bcl_bhuiyan/`:

```bash
python manage.py check
python manage.py test bcl --verbosity 2
python manage.py manage_testbank --initialize --dry-run
python manage.py manage_testbank --initialize
python manage.py manage_testbank --audit
python manage.py manage_testbank --import-json sample_test.json --dry-run
python manage.py manage_testbank --import-json sample_test.json
```

`--initialize` is idempotent and never overwrites existing test numbers. `--import-json` refuses existing test numbers, including initialized slots; use Django Admin to populate initialized slots, or import first and initialize remaining slots afterwards. JSON imports are atomic. `--publish` refuses incomplete exams. Uploaded audio/image files must be attached via Django Admin, not arbitrary JSON paths. Readiness is a structural check, not an editorial or copyright review. Existing published tests are audited but not automatically unpublished.

## Example JSON schema (incomplete demonstration; do not publish)

```json
{
  "test_number": 1,
  "title": "Authorized Practice Test 1",
  "description": "Client-provided practice content",
  "modules": [
    {
      "module_type": "reading",
      "duration_minutes": 60,
      "sections": [
        {
          "title": "Reading Passage 1",
          "passage": "Authorized passage text",
          "questions": [
            {
              "question_type": "mcq",
              "question_text": "Example question?",
              "correct_answer": "B",
              "options": [
                {"option_key": "A", "option_text": "First", "is_correct": false},
                {"option_key": "B", "option_text": "Second", "is_correct": true}
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

For a structurally ready test provide 3 Reading sections / 40 questions, 4 Listening sections / 40 questions with uploaded audio, and 2 Writing sections / 2 essay questions. Reading sections need passages; automatic-scored questions need keys. Matching questions are rejected for readiness because the current scoring engine does not support them. Publishing should be done only after manual review and successful candidate end-to-end tests.
