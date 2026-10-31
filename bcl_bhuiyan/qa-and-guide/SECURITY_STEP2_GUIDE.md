# Production Security Step 2 — Authentication and MFA

## Deployment
Install requirements, run `python manage.py migrate`, `python manage.py check`, and `python manage.py test bcl.test_security_step2 --verbosity 2`.
Run the full regression suite: `python manage.py test bcl --verbosity 2`.
Staff logins are redirected to TOTP enrollment and must verify a six-digit code before accessing staff pages or Django Admin. Keep provisioning URIs confidential.
Database-backed django-axes tracks failed login attempts. Verify lockouts against both candidate login and Django Admin.
Use HTTPS in production; restrict staff provisioning and have a documented lost-device recovery procedure.

## Risks requiring review
* django-otp TOTP keys are stored in the database: protect database and backups with encryption and strict access controls.
* TOTP codes can be phished; consider WebAuthn for stronger staff authentication.
* Enrollment and OTP verification endpoints are not independently throttled by django-axes; configure reverse-proxy rate limiting before public deployment.
* Verify that the axes lockout policy behaves correctly behind the real reverse proxy.
* No production penetration test or disaster recovery rehearsal has been performed.
