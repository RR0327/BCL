# IELTS Platform — Phase 4 export reconciliation and next-stage readiness

This update restores missing PDF/DOCX Writing report exports in the uploaded baseline.
It does NOT claim that Phase 5 has been completed. Existing data and application code are preserved.

## Modified or new files
- bcl_bhuiyan/bcl/writing_exports.py
- bcl_bhuiyan/bcl/urls.py
- bcl_bhuiyan/templates/writing/review_detail.html
- bcl_bhuiyan/templates/writing/review_list.html
- bcl_bhuiyan/bcl/test_writing_exports.py
- bcl_bhuiyan/requirements.txt

## Installation (Windows PowerShell)
cd D:\Vs_Code\Sakib-bhai\bcl_bhuiyan
python -m pip install -r requirements.txt
python manage.py check
python manage.py makemigrations bcl --check --dry-run
python manage.py test bcl --verbosity 2
python manage.py runserver

Staff-only download URLs are linked from /writing/reviews/<attempt-id>/ .
A submitted Writing attempt is required; in-progress attempts cannot be exported.
No migration is required by this update.

## Verification
[ ] Django check passes
[ ] No unexpected migrations
[ ] All legacy Django tests pass
[ ] Seven export regression tests pass
[ ] Staff can download PDF and DOCX from submitted Writing attempt
[ ] PDF opens and contains both responses
[ ] DOCX opens and contains both responses
[ ] Candidate and anonymous accounts cannot export
[ ] In-progress attempts cannot export
[ ] Reading, Listening and Writing exam regression flows pass

## Limitations
- PDF text uses ReportLab standard font; non-Latin glyphs may require configured Unicode fonts.
- PDF/DOCX exports omit embedded task images; prompts and answers are exported as text.
- Production deployment, 30-test ingestion and full security audit are still pending.
- Local full Django tests were not executed in this packaging environment.
