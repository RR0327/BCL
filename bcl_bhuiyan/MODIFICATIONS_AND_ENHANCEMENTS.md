# Project Modifications and Enhancements

This document provides a comprehensive record of all key modifications, bug fixes, UI/UX polish, and feature enhancements implemented across the **IELTS Mock Test Platform** codebase.

---

## 1. Executive Summary

The project underwent extensive stabilization, anti-cheating hardening, staff workflow improvements, and light/dark theme polish to create a production-ready, computer-delivered IELTS preparation portal.

Key focal areas:
- **Exam Integrity**: Automated focus-loss detection and a 3-strike tab-switch violation policy.
- **Staff Evaluation**: High-precision numeric rubric scoring replacing multiple-choice dropdowns.
- **Admin Usability**: Restoration of the standard Django Admin navigation sidebar and removal of redundant nested sidebars.
- **Authentication & Navigation**: Intuitive "Back to Home" navigation across login, registration, and MFA pages.
- **Theme System**: Complete dark mode refinement across the homepage, navigation, practice cards, and security checkpoints.
- **Data Portability**: Full UTF-8 database serialization (`database_content_export.json`) supporting seamless device migration.

---

## 2. Exam Anti-Cheating & Violation Auto-Submission

### Problem
Candidates taking an exam could switch tabs or minimize the browser window. While a modal warning appeared, the violation count did not automatically submit the exam on the third violation, allowing candidates to potentially continue indefinitely.

### Modifications Implemented
1. **Frontend Focus Monitoring (`static/js/exam.js`)**:
   - Added robust event listeners for `document.visibilitychange` (`hidden`) and `window.blur`.
   - Configured an in-memory violation counter that tracks tab switches and focus losses.
   - Implemented a 3-strike progression:
     - **Strike 1**: Warning modal: *"Warning 1 of 2: Please stay on this tab during your exam."*
     - **Strike 2**: Warning modal: *"Warning 2 of 2: Final Warning! Switching tabs one more time will automatically submit your exam."*
     - **Strike 3**: Automatic trigger: locks the interface, displays *"Exam auto-submitted due to repeated violations"*, and dispatches an immediate POST to `/exam/session/<attempt_id>/violation/`.
2. **Backend Enforcement (`bcl/exam_views.py`)**:
   - `report_exam_violation` validates the attempt status and increments the server-side violation log.
   - Upon the 3rd focus-loss strike, the backend automatically sets `attempt.status = "auto_submitted"`, records `submitted_at = timezone.now()`, and returns a JSON payload directing the browser to the submission ended view (`/exam/session/<attempt_id>/ended/`).
3. **Automated Test Coverage (`bcl/tests.py`)**:
   - Implemented `ExamFocusLossTests` asserting:
     - Warning state progression on strikes 1 and 2.
     - State transition to `auto_submitted` on strike 3.
     - Prevention of post-submission answers or further tampering.

---

## 3. Staff Writing Evaluation & Scoring Rubric

### Problem
When evaluating candidate IELTS Writing submissions, staff examiners were restricted to multiple-choice dropdown (`<select>`) menus that were clunky to navigate and inflexible for fractional scoring.

### Modifications Implemented
1. **Numeric Text Field (`templates/writing/review_detail.html`)**:
   - Converted the score inputs from `<select>` dropdowns into modern HTML5 numeric fields:
     ```html
     <input type="number" 
            name="score_{{ task.id }}_{{ criterion }}" 
            class="score-input"
            step="0.5" 
            min="0" 
            max="9" 
            placeholder="e.g. 6.5" 
            required>
     ```
   - Covers all four IELTS assessment criteria:
     1. **Task Achievement / Task Response** (TR)
     2. **Coherence & Cohesion** (CC)
     3. **Lexical Resource** (LR)
     4. **Grammatical Range & Accuracy** (GRA)
2. **Backend Decimal Parsing (`bcl/writing_views.py`)**:
   - Updated score parsing to accept Decimal inputs rounded to half-band intervals (e.g., 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0).
   - Validates that values fall strictly within the IELTS 0.0–9.0 range.
3. **Dark Mode & Focus States (`static/css/theme.css`)**:
   - Added dark slate styling (`background: #0f172a; border-color: #334155; color: #f8fafc;`) with an indigo focus ring (`#6366f1`) for both light and dark modes.

---

## 4. Admin Portal Usability & Navigation

### Problem
- The Django Admin index page (`/admin/`) was missing the standard collapsible left navigation sidebar (`nav-sidebar`), requiring staff to navigate manually.
- A redundant, squished card labeled *"Exam Portal Models & Configuration"* occupied excessive space in the center index view.
- In question reviews, the layout made it difficult to clearly distinguish between question prompts and candidate answers.

### Modifications Implemented
1. **Restored Navigation Sidebar (`templates/admin/base_site.html` & `templates/admin/index.html`)**:
   - Ensured Django's native `nav-sidebar` is included on the admin root page so staff can quickly jump between Models, Users, Attempts, and Modules.
2. **Removed Redundant Inner Sidebar Card**:
   - Eliminated the awkward inner card that cluttered `templates/admin/index.html`.
3. **Clear Question vs. Answer Distinctions**:
   - Styled question prompts and candidate answers with distinct visual containers, colored borders (blue accent for prompts, green/slate for answers), and clear badges.

---

## 5. Authentication & Navigation Flow

### Problem
Candidates and staff navigating to `/login/` or `/register/` had no convenient way to return to the public homepage without manually modifying the URL.

### Modifications Implemented
1. **"Back to Home" Buttons (`templates/registration/login.html` & `templates/registration/register.html`)**:
   - Added a top-left action button with an SVG arrow icon (`← Back to Home`) inside the `.auth-top-nav` bar.
   - Added a secondary centered text link in the footer (`Return to Homepage`).
   - Added smooth micro-animations (`transform: translateX(-2px)`) on hover.
2. **Consistent Header Bar**:
   - Aligned the theme toggle button `#themeToggleBtn` side-by-side with the back button across all auth views.

---

## 6. Homepage Dark Mode Overhaul

### Problem
The homepage displayed glaring visual bugs when toggling to dark mode:
- The entire middle `.modules` practice section stayed bright white/light-blue (`#f4f7fc`) while hero and about sections were dark.
- The `Mock` portion of `IELTSMock` rendered in dark navy (`#1645a1`), making it unreadable.
- Navbar buttons had poor contrast: the Login button had dark navy text and flashed white on hover.
- Section eyebrows had hardcoded dark styles or inline `style="color: #1645a1;"`.
- `.coming-soon` lacked badge padding and borders.

### Modifications Implemented
1. **Practice Modules Background (`static/css/theme.css`)**:
   ```css
   html.dark .modules,
   html[data-theme="dark"] .modules {
       background: #0b0f19 !important;
       border-top: 1px solid #1e293b !important;
       border-bottom: 1px solid #1e293b !important;
   }
   ```
2. **High-Contrast Brand Logo**:
   - `.logo span` and `.auth-logo span` set to vibrant sky blue (`#60a5fa`) in dark mode.
3. **Navbar Buttons (`templates/home.html` & `static/css/theme.css`)**:
   - **Login**: Outlined in `#3b82f6` with sky blue text (`#93c5fd`) and subtle dark hover (`rgba(59, 130, 246, 0.18)`).
   - **Register / Dashboard**: Vibrant primary blue (`#2563eb`) with `#1d4ed8` hover.
   - **Logout**: Dark slate button (`#1e293b`) with border (`#475569`).
   - **Welcome User**: Light slate text (`#cbd5e1`).
4. **Pill Badges & Eyebrows**:
   - Transformed `.coming-soon` into a pill badge (`padding: 5px 14px; border-radius: 9999px; font-size: 12px; font-weight: 700;`).
   - Replaced inline style on About eyebrow with `.about-eyebrow`, rendering `#1645a1` in light mode and `#818cf8` in dark mode.
5. **Notification Banners**:
   - Dark mode styles for `.homepage-message` (translucent emerald for success, dark crimson for errors).

---

## 7. Staff Two-Factor Authentication (MFA) Page Overhaul

### Problem
The staff verification screen (`templates/security/mfa.html`) was completely bare. The "Verify" and "Log out" buttons were stacked directly against each other into an ugly, squished blue block, and the input was an unformatted text bar.

### Modifications Implemented
1. **Unified Design System**:
   - Integrated `auth.css` and `theme.css` tokens.
   - Added security shield badge icon (`STAFF SECURITY`) and clear explanatory subtitle.
2. **Dedicated 6-Digit OTP Input**:
   - Centered large numerals (`font-size: 26px`), wide letter-spacing (`10px`), and monospace typography.
   - Added helper hint: *"Enter the current 6 numbers shown in your authenticator app"*.
3. **Action Separation**:
   - **Primary Action**: Prominent full-width **Verify** button with hover elevation.
   - **Secondary Action**: Placed **Log out** in a separated footer row below a divider line (`.mfa-footer-divider`), styled as a ghost button with a logout icon that highlights red on hover.
4. **Navigation & Theme Controls**:
   - Integrated top "Back to Home" button and the theme toggle button `#themeToggleBtn`.

---

## 8. Verification & Test Suite Results

All 262 automated tests in the test suite pass cleanly:
```bash
python manage.py test
----------------------------------------------------------------------
Ran 262 tests in 160.540s

OK (skipped=1)
```

The application is completely verified for frontend responsiveness, dark mode contrast, backend data integrity, and role-based access security.
