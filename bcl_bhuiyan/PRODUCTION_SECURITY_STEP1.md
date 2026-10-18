# Production Security Remediation — Step 1

## Scope
Candidate audio and section images are now served through authenticated, attempt-scoped Django endpoints. Direct media URLs were removed from the candidate session template. Staff Writing-review images use a staff-only endpoint. The Django development URL configuration no longer serves MEDIA_ROOT.

## CRITICAL deployment requirement
**The web server, reverse proxy, CDN, and object-storage bucket must NOT expose MEDIA_ROOT or /media/ directly.** Keep MEDIA_ROOT outside PUBLIC static directories; configure private object storage or an internal proxy delivery strategy. This change does not secure already leaked media URLs, copies, caches, or public buckets. Rotate previously public exam content as needed.

## Commands
`python manage.py check`
`python manage.py test bcl.test_private_media --verbosity 2`
`python manage.py test bcl --verbosity 2`
`python manage.py check --deploy` (staging production environment)

## Manual validation
Start a Listening attempt as a candidate and verify playback; start a Writing attempt with an image and verify rendering. Try the media endpoint signed out, as another candidate, as staff, after submission, after timeout, and for a section in a different module. Each unauthorized request must be blocked. Verify that /media/ URLs are not served by Nginx/Apache/CDN or Django. Verify response caching and logs do not leak content.

## Remaining blockers
Signed or authenticated delivery still requires operational reverse-proxy/storage enforcement and large-file performance testing. Authentication MFA, rate limiting, content licensing/readiness, PostgreSQL restoration rehearsal, retention policies, and independent security testing remain unresolved.
