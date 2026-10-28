# Database Setup & Testing Guide: Complete Step-by-Step Instructions

This guide provides end-to-end instructions for setting up the **IELTS Mock Test Platform** from scratch on a new computer, loading the exported JSON database, and executing all automated tests.

---

## 1. What to Bring to the New Computer

Before switching devices, ensure you have copied the following key assets:
1. **Repository folder**: The entire `bcl_bhuiyan` project folder.
2. **Exported Database JSON files**:
   - `database_content_export.json` *(Clean fixtures containing all 475 core objects: users, tests, modules, sections, questions, options, attempts, evaluations, and audit events)*.
   - `database_export.json` *(Full raw dump including historical session logs)*.
3. **Media directory (`media/`)**:
   - Contains audio listening tracks (`media/ielts/audio/`), question diagrams, and task images.
4. **Secret values**:
   - Your custom database password and Django `SECRET_KEY`.

---

## 2. Prerequisites on the New Device

Install the following software on the new computer:
- **Python 3.11, 3.12, or 3.13** (64-bit) from [python.org](https://www.python.org/). Check: `python --version`.
- **Git** from [git-scm.com](https://git-scm.com/).
- **Database Engine** (choose one):
  - **SQLite** *(Recommended for fastest, zero-installation local setup)*: Built into Python, no external installation needed!
  - **PostgreSQL 15 or 16** *(Recommended for production-like staging)*: Download from [postgresql.org](https://www.postgresql.org/download/).

---

## 3. Database Setup from First to Last

Follow these steps in order in your terminal (PowerShell or Bash):

### Step 1: Open Project Directory
```powershell
cd path\to\BCL-Bhuiyan\bcl_bhuiyan
```

### Step 2: Create & Activate Virtual Environment
```powershell
# Create virtual environment
python -m venv venv

# Activate on Windows (PowerShell)
.\venv\Scripts\Activate.ps1

# (If PowerShell displays execution policy error, run once: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass)

# Upgrade pip
python -m pip install --upgrade pip
```

### Step 3: Install Project Dependencies
```powershell
pip install -r requirements.txt
```

### Step 4: Configure the Environment File (`.env`)
Create a `.env` file in the project root (`bcl_bhuiyan/.env`).

#### Option A: Quickstart with SQLite (Zero Configuration)
```env
DJANGO_DEBUG=True
DJANGO_SECRET_KEY=django-insecure-generate-any-random-key-here-for-local-use
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

# SQLite configuration
DB_ENGINE=sqlite3
DB_NAME=db.sqlite3

APP_NAME=IELTS Mock Test Platform
LANGUAGE_CODE=en-us
TIME_ZONE=Asia/Dhaka

SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
DJANGO_SECURE_SSL_REDIRECT=False
```

#### Option B: PostgreSQL Setup
If using PostgreSQL, first create the database and user via `psql`:
```sql
CREATE USER ielts_app WITH PASSWORD 'YourStrongPassword!';
CREATE DATABASE ielts_db OWNER ielts_app;
GRANT ALL PRIVILEGES ON DATABASE ielts_db TO ielts_app;
```
Then configure your `.env`:
```env
DJANGO_DEBUG=True
DJANGO_SECRET_KEY=django-insecure-generate-any-random-key-here-for-local-use
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

# PostgreSQL configuration
DB_ENGINE=postgresql
DB_NAME=ielts_db
DB_USER=ielts_app
DB_PASSWORD=YourStrongPassword!
DB_HOST=127.0.0.1
DB_PORT=5432
DB_SSLMODE=prefer

APP_NAME=IELTS Mock Test Platform
LANGUAGE_CODE=en-us
TIME_ZONE=Asia/Dhaka

SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
DJANGO_SECURE_SSL_REDIRECT=False
```

---

### Step 5: Run Database Migrations
Create all database tables, foreign keys, and indexes:
```powershell
python manage.py migrate
```
*(All migrations from `0001_initial` through `0011_fullmockattempt_candidateattempt_full_mock` will execute).*

---

### Step 6: Import Data from the JSON Export
Load all IELTS tests, practice modules, sections, questions, options, and candidate history into the fresh database:
```powershell
python manage.py loaddata database_content_export.json
```
**Expected Output:**
```text
Installed 475 object(s) from 1 fixture(s)
```
*(This loads both full mock exams, all Reading, Listening, and Writing modules, 51 questions, 105 question options, and sample attempts cleanly with zero data conflicts).*

---

### Step 7: Create or Verify Superuser
If you need a fresh administrator account:
```powershell
python manage.py createsuperuser
```
Follow the prompts to specify username, email, and password.

---

### Step 8: Collect Static Assets
Compile all stylesheets (including light/dark themes), JavaScript files, and fonts:
```powershell
python manage.py collectstatic --noinput
```

---

### Step 9: Start the Development Server
```powershell
python manage.py runserver
```
Visit **`http://127.0.0.1:8000/`** in your browser.
- **Home**: `http://127.0.0.1:8000/`
- **Candidate Login**: `http://127.0.0.1:8000/login/`
- **Candidate Dashboard**: `http://127.0.0.1:8000/dashboard/`
- **Admin Portal**: `http://127.0.0.1:8000/admin/`
- **Writing Reviews Queue**: `http://127.0.0.1:8000/writing/reviews/`

---

## 4. All Testing Information & Execution Guide

The platform includes **262 automated tests** covering anti-cheating, score calculations, security middleware, MFA, admin tools, and database concurrency.

### Running the Complete Test Suite
To run all 262 tests in one command:
```powershell
python manage.py test
```
**Expected Result:**
```text
Found 262 test(s).
Creating test database for alias 'default'...
......................................................................
----------------------------------------------------------------------
Ran 262 tests in 160.540s

OK (skipped=1)
```

---

### Running Specific Test Suites

#### 1. Exam Violation & 3-Strike Auto-Submission Tests
Tests the focus-loss detection, warning increments, and automatic submission on strike 3:
```powershell
python manage.py test bcl.tests.ExamFocusLossTests
```

#### 2. Staff Two-Factor Authentication (MFA) & Security Middleware
Tests MFA enrollment, TOTP verification, session cycle, and route protection:
```powershell
python manage.py test bcl.test_security_step2 bcl.test_security_step3 bcl.test_security_step4
```

#### 3. Admin Portal Usability & Navigation Tests
Tests the admin left navigation sidebar, question rendering, and attempt dashboards:
```powershell
python manage.py test bcl.test_admin_usability bcl.test_admin_dashboard_results
```

#### 4. Writing Evaluation Rubric & Export Tests
Tests fractional decimal scoring (0.0 to 9.0 in 0.5 steps) and export formats (PDF, Excel, JSON):
```powershell
python manage.py test bcl.test_review_and_variants bcl.test_writing_exports
```

#### 5. Question Testbank & Exam Module Integrity
Tests Reading passages, Listening audio playback configs, multiple-choice, matching, and fill-in-the-blank variants:
```powershell
python manage.py test bcl.test_testbank bcl.test_phase5_quality
```

#### 6. PostgreSQL Concurrency & Anti-Race Condition Tests
*(When running on PostgreSQL)* tests multi-worker lock contention and concurrent answer submissions:
```powershell
python manage.py test bcl.test_step6k_postgres_concurrency bcl.test_step6l_postgres_races
```

#### 7. Media & Exam Asset Verification
Verifies private media token access and audio integrity:
```powershell
python manage.py test bcl.test_private_media bcl.test_step6m_exam_assets
```

---

## 5. Troubleshooting & FAQs

### Q: `python manage.py loaddata` says `Invalid start byte` or character error?
- **Fix**: Use `database_content_export.json`. It is strictly formatted in UTF-8 without system-specific encoding issues.

### Q: Staff login redirects to `/security/mfa/verify/` and asks for a code?
- **Fix**: Staff users require two-factor authentication.
  - If you need to generate the 6-digit TOTP code in Python for testing:
    ```powershell
    python -c "import os, django; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bcl_bhuiyan.settings'); django.setup(); from django.contrib.auth import get_user_model; from django_otp.plugins.otp_totp.models import TOTPDevice; from django_otp.oath import totp; u = get_user_model().objects.filter(is_staff=True).first(); d = TOTPDevice.objects.get(user=u); print('Current OTP:', str(totp(d.bin_key, step=d.step, t0=d.t0, digits=d.digits)).zfill(d.digits))"
    ```
  - Or create a non-staff candidate account to test the student portal without MFA requirements.

### Q: Static styling looks unstyled or outdated?
- **Fix**: Run `python manage.py collectstatic --noinput` to refresh WhiteNoise compiled assets.

### Q: How do I switch between SQLite and PostgreSQL?
- **Fix**: Simply toggle `DB_ENGINE=sqlite3` or `DB_ENGINE=postgresql` in your `.env` file. Django automatically routes queries based on the active `.env` configuration.
