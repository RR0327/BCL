# IELTS Mock Test Platform

An exam-focused Django platform for practicing computer-delivered IELTS
Listening, Reading, and Writing modules. The application supports individual
module practice, sequential Full Mock Tests, answer review, automated scoring,
Writing evaluation workflows, and staff-managed test content.

> **Project status:** Active development. The platform is designed for local
> development and can be configured for a production deployment with
> PostgreSQL, HTTPS, secure cookies, WhiteNoise, and Waitress.

## Features

### Candidate experience

- Candidate registration, login, logout, and dashboard
- Individual Listening, Reading, and Writing examinations
- Full Mock Test workflow:
  - Listening examination and answer review
  - Reading examination and answer review
  - Writing examination
  - Consolidated overall result
- Partial Full Mock results when a candidate stops after a completed module
- Every new Full Mock attempt starts from the Listening module
- Timed examinations with server-side expiry handling
- Autosaving answers during an active examination
- Question navigation and exam progress tracking
- Focus-loss/tab-switch monitoring and violation reporting
- Detailed answer scripts, correct answers, explanations, and score information
- Writing feedback and staff review pages
- Light/dark theme switcher and responsive navigation

### Staff and administration

- Django admin interface for managing:
  - Mock tests
  - Exam modules and sections
  - Questions and answer options
  - Listening audio, Reading passages, and question media
  - Writing reviews and evaluations
- Test-bank readiness and asset audit commands
- Candidate result and Full Mock export commands
- Private media endpoints protected by authentication and authorization
- Optional staff MFA using Django OTP

### Security and operational safeguards

- CSRF protection and secure session configuration
- HTTP-only, SameSite cookies
- Login rate limiting and lockout through `django-axes`
- Optional HTTPS redirect and HSTS configuration
- Trusted proxy support controlled by environment configuration
- Clickjacking and content-type sniffing protection
- Candidate ownership checks for attempts, results, media, and exports
- SQLite backup and encrypted-backup management commands

## Technology Stack

- **Backend:** Python, Django 4.2 LTS
- **Database:** SQLite for local development or PostgreSQL for deployment
- **Frontend:** Django Templates, HTML, CSS, and vanilla JavaScript
- **Static files:** WhiteNoise with compressed manifest storage
- **Documents and exports:** WeasyPrint, ReportLab, and python-docx
- **Authentication/security:** Django authentication, django-axes,
  django-otp, and cryptography
- **Production WSGI server:** Waitress

## Project Structure

```text
.
├── README.md
└── bcl_bhuiyan/
    ├── manage.py
    ├── requirements.txt
    ├── .env.example
    ├── bcl/
    │   ├── admin.py              # Staff content-management interface
    │   ├── exam_views.py         # Exam and Full Mock workflows
    │   ├── models.py             # Test, question, attempt, and result models
    │   ├── scoring.py            # Listening and Reading scoring logic
    │   ├── private_media.py      # Protected exam media delivery
    │   ├── writing_views.py      # Writing review workflows
    │   ├── management/commands/  # Audits, backups, imports, and release checks
    │   └── test_*.py             # Automated regression and security tests
    ├── bcl_bhuiyan/
    │   ├── settings.py
    │   ├── urls.py
    │   ├── asgi.py
    │   └── wsgi.py
    ├── templates/
    ├── static/
    └── media/
```

## Requirements

- Python 3.10 or newer
- pip
- SQLite for the default local setup, or PostgreSQL 13+ for deployment
- A modern browser with JavaScript enabled

Database-configured Listening tests can be created entirely from Django Admin:
create a mock test, add a Listening module, upload module or section audio,
add sections and questions with answer keys, and publish the test. Legacy
Listening tests that have no database sections continue to use their existing
HTML assets during migration.

For production, set `MEDIA_ROOT` to a persistent mounted volume (or configure
your deployment's storage-backed filesystem). Uploaded audio and exam images
must not live only in an ephemeral application container. Keep media private;
the application serves candidate media through authenticated endpoints.

## Local Development Setup

### 1. Clone the repository

```bash
git clone https://github.com/Sakib232/BCL.git
cd BCL/bcl_bhuiyan
```

### 2. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy the example configuration:

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS/Linux:

```bash
cp .env.example .env
```

Generate a secure Django secret key:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Set the generated value as `DJANGO_SECRET_KEY` in `.env`. For local
development, the default SQLite configuration is sufficient:

```dotenv
DJANGO_SECRET_KEY=your-generated-secret-key
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
DB_ENGINE=sqlite3
DB_NAME=db.sqlite3
MEDIA_ROOT=/var/lib/bcl_bhuiyan/media
```

### 5. Apply migrations

```bash
python manage.py migrate
```

### 6. Create an administrator

```bash
python manage.py createsuperuser
```

### 7. Start the development server

```bash
python manage.py runserver
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in a browser.
The administration interface is available at
[http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/).

## Content Setup

1. Sign in to the Django admin as a staff user.
2. Create an `IELTS Mock Test`.
3. Add active Listening, Reading, and Writing modules.
4. Add sections and questions to each module.
5. Configure answer keys for automatically scored questions.
6. Upload audio, passage images, question images, and other required media.
7. Run the relevant audit commands before publishing the mock test.

For a Full Mock Test, active modules are presented in this order:
**Listening → Reading → Writing**.

## Useful Management Commands

Run these commands from `bcl_bhuiyan/`:

```bash
# Check Django configuration
python manage.py check

# Collect production static assets
python manage.py collectstatic --noinput

# Audit candidate workflow data
python manage.py audit_candidate_workflows

# Audit published test assets
python manage.py audit_exam_assets

# Check test-bank readiness
python manage.py preflight_testbank

# Run release acceptance checks
python manage.py release_acceptance

# Run release and environment checks
python manage.py release_check

# Create a SQLite backup
python manage.py backup_sqlite
```

Run `python manage.py help` to see all available project commands.

## Testing

Run the complete Django test suite:

```bash
python manage.py test
```

Run selected suites while developing:

```bash
python manage.py test bcl.tests
python manage.py test bcl.test_phase5_security
python manage.py test bcl.test_phase5_quality
python manage.py test bcl.test_architecture_listening
```

Before opening a pull request, also run:

```bash
python manage.py check
git diff --check
```

## Production Configuration

Set `DJANGO_DEBUG=False` and provide an explicit host list. PostgreSQL is
recommended for multi-user deployments:

```dotenv
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=example.com,www.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://example.com
DJANGO_SECRET_KEY=unique-production-secret

DB_ENGINE=postgresql
DB_NAME=ielts
DB_USER=ielts_app
DB_PASSWORD=database-password
DB_HOST=localhost
DB_PORT=5432
DB_SSLMODE=require
```

Recommended deployment sequence:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
```

Serve the application through a TLS-terminating reverse proxy and run the
configured WSGI application with Waitress or another supported production
server. Do not expose Django's development server to the public internet.

## Data and Media Notes

- `db.sqlite3` is intended for local development and is ignored by Git.
- Uploaded media is stored under `media/` and should use persistent,
  access-controlled storage in production.
- Static assets are collected into `staticfiles/` during deployment.
- Keep `.env`, database backups, uploaded private media, and generated exports
  out of source control.

## Contributing

1. Create a focused branch from the current development branch.
2. Keep changes scoped to the requested feature or fix.
3. Add or update regression tests for behavior changes.
4. Run Django checks and the relevant test suites.
5. Review the diff for secrets, generated files, and unrelated changes.
6. Open a pull request with a concise description and validation results.

## License

No license has been declared for this repository. Until a license is added,
the source should be treated as proprietary and should not be redistributed
or reused outside the repository's authorized permissions.
