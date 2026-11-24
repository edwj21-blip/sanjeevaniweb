# SANJEEVANI – update notes, setup and honest test report

> **Read this first.** The code in this ZIP was written in a sandbox **without internet access, so Django
> could not be installed and the project has never been run there**. Everything below under
> "What I verified" was actually executed; everything under "NOT verified" you must run on your PC
> (commands are in section 3). Expect to fix a few small errors on first run – please send me the
> traceback and I will fix it.

## 1. What changed (existing project modified, not rebuilt)

**Kept:** the `core` app, `DonorProfile`, `DonorContactRequest`, `HospitalLocationDetails`, `Notification`,
contact/abuse/activity models, mobile-number login, Django admin, `render.yaml` / `build.sh` (untouched –
no hosting work was done).

**New models** (migration `0002`, includes a data step that turns every existing donor's
`last_donation_date` into a history record): `DonationRecord`, `EligibilitySettings` (editable interval),
`Reminder`, `PushSubscription`. New `DonorProfile` fields: `date_of_birth`, `next_eligible_date`,
`eligibility_hold`, `hold_reason`, `health_declaration`, `notify_reminders`. Hospital model gained
`latitude`, `longitude`, `place_id`.

| Area | How it works |
|---|---|
| 18+ check | DOB required; exact age (birthday-aware) validated in the browser (`main.js`) **and** in Django (`forms.py`, `eligibility.py`). Exact English/Malayalam messages from your spec. |
| Search | Public. Shows Available **and** Unavailable donors; unavailable get a red badge, a disabled "Currently Unavailable" button and their next eligible date. Donors with no DOB on file are hidden until they add it. |
| Availability | Never typed in by the donor. `services.recalc_donor()` derives it from donation history + `EligibilitySettings`. Re-activation happens automatically (`refresh_due_donors()` runs on page loads, via the optional middleware, and via `run_scheduled_jobs`). An admin **eligibility hold** blocks re-activation. |
| Interval | Stored in the database (Admin → Eligibility Settings), per donation type. **Defaults are 90 days for all three types and are marked "not validated"** until you record who confirmed them. I did not assert any medical period – please have your blood bank / doctor confirm. |
| Confirmation flow | Call Now → server records request → dialer opens via `tel:` → on return the receiver is asked "Did you connect?" → Yes creates the donor request → donor popup (polled every 5 s) → accept/decline stored once → receiver popup. All DB-backed, CSRF-protected, duplicate-safe. |
| Hospital | `hospital_select.html` + `hospital.js`: Google Maps JS API, Places (new `Place.searchByText/searchNearby`), Geocoding, draggable marker, manual entry fallback. Navigation URL is built server-side from the saved coordinates. |
| WhatsApp | Only on the hospital-share page: prefilled Click-to-Chat message in the exact format you gave. Old WhatsApp confirmation pages/routes were removed. |
| Reminders | One `Reminder` per donor/target date (DB unique constraint), 7 days before; replaced when a new donation is recorded; in-app notification + Web Push; no daily reminders, no WhatsApp/SMS/email. |
| Web push | Service worker at `/sw.js`, VAPID, subscribe/unsubscribe endpoints, expired (404/410) subscriptions deactivated, delivery status stored on the reminder. Optional – never forced. |
| Admin | Django admin extended (donation records, eligibility settings, reminders, subscriptions, hold, recalculate action) + `/staff/dashboard/` (stats, blood group/district tables, search, duplicates, recent confirmations/reminders). Donor and donation records cannot be deleted from admin (cancel a donation instead). |
| Language | `core/translations.py` (plain Python dict, no `.mo` compiling) + `{% t "..." %}` tag. Every string used in templates/views is covered (checked by script). **Needs proof-reading by a Malayalam speaker.** |
| UI | New simple stylesheet (medical red, white, grey, Inter + Noto Sans Malayalam, no heavy gradients), mobile first. |

**Decisions I made that you may want to change**
1. *Call Now requires login* (anonymous users see "Login to Call"). Searching is fully public. Reason: it
   needs a receiver identity for the confirmation flow, and it keeps donor numbers out of public HTML.
   I added a light **receiver sign-up** (`/signup/`) for people who need blood but are not donors.
2. The donor's number is sent only to the logged-in caller's browser (to open the dialer) – a determined
   logged-in user could still collect numbers. A per-receiver limit of 20 requests/day is enforced.
3. No-history donors: available only if they ticked the health declaration (policy configurable).

## 2. Files

**Added:** `core/eligibility.py`, `core/services.py`, `core/translations.py`, `core/middleware.py`,
`core/templatetags/sj.py`, `core/migrations/0002_donor_eligibility_donations_reminders_push.py`,
management commands `run_scheduled_jobs`, `recalculate_availability`, `generate_vapid_keys`,
`static/js/hospital.js`, `templates/sw.js`, `templates/_field.html`, `templates/_check.html`,
`templates/auth/signup.html`, `templates/dashboard/{admin_dashboard,donation_update,donation_history,notification_settings}.html`,
`templates/donors/{hospital_select,hospital_share}.html`, this file.

**Modified:** `core/{models,views,urls,forms,admin,context_processors,tests}.py`,
`core/management/commands/create_sample_data.py`, `sanjeevaniweb/settings.py`, `requirements.txt`,
`.env.example`, `static/css/main.css`, `static/js/main.js`, and all other templates.

**Removed (replaced):** `templates/donors/{contact,hospital_location,hospital_location_preview,whatsapp_confirm}.html`
and the WhatsApp-confirmation views/URLs.

## 3. Easiest way: double-click `run.bat`
`run.bat` does everything: creates the virtual environment, installs packages, creates `.env` with a random
secret key and push keys (`setup_env.py`), runs `check` + `migrate`, asks once whether to create demo donors
and an admin login, starts the background scheduler window (reminders + automatic availability every
10 minutes) and the website at http://127.0.0.1:8000. Add `GOOGLE_MAPS_API_KEY=...` to `.env` and restart.
`run_tests.bat` runs the migration-consistency check and the automated tests (run `run.bat` once first).
If anything fails the window stays open - send me the message.

### Or manually in PowerShell

```powershell
cd path\to\sanjeevaniweb
python -m venv venv
.\venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
copy .env.example .env

python manage.py generate_vapid_keys   # paste the 3 lines into .env
# edit .env: add GOOGLE_MAPS_API_KEY=...

python manage.py check
python manage.py makemigrations --check --dry-run   # must say "No changes detected"
python manage.py migrate
python manage.py test core -v 2                       # automated tests
python manage.py create_sample_data                   # 15 demo donors, password Sanjeevani@123
python manage.py createsuperuser
python manage.py runserver
```
Then in **Admin → Eligibility Settings** set the validated interval and who confirmed it.
Scheduler (so reminders go out even if nobody visits): run `python manage.py run_scheduled_jobs`
daily/hourly from Windows Task Scheduler. After changing eligibility settings the admin save recalculates
everyone; manual: `python manage.py recalculate_availability`.

### Google Maps setup
Google Cloud Console → new project → **enable billing** → enable *Maps JavaScript API*, *Places API (New)*,
*Geocoding API* → create an API key → restrict by HTTP referrer (`http://127.0.0.1:8000/*`,
`http://localhost:8000/*`, your future domain) and to those three APIs → put it in `.env` as
`GOOGLE_MAPS_API_KEY`. Check current pricing/free credit in the console; the code does not hide costs.
Without a key the page still works with manual name/address/coordinates entry.

### Web push
Needs `pywebpush` (in requirements) and the VAPID keys in `.env`. Works on `http://localhost` and on HTTPS
only. Delivery is best effort and depends on browser/OS/push service.

## 4. Testing report

### What I verified (actually executed in the sandbox)
- `core/eligibility.py`: age at exact birthday, day before birthday, 29-Feb births, 18-year cut-off,
  interval boundary (day 89 not eligible / day 90 eligible), hold blocks, blank history not assumed
  eligible, policy switch – **all assertions passed**.
- VAPID key generation logic (P-256, 65-byte public key, DER private key round-trip) – **passed**.
- Every Python file byte-compiles; `main.js`, `hospital.js`, `sw.js` pass `node --check`.
- Static template check: `if/for/block/with` tags balanced, every `{% url %}` name exists, every URL maps to a
  real view, every `{% t %}` tag well-formed, `{% load sj %}` present – **0 problems**.
- Translation coverage: all 245 strings used in templates/views/forms have Malayalam entries – **0 missing**.

### NOT verified (could not be run here) – please run section 3
Django `check`, migrations (the hand-written `0002` is guarded by a test that fails if it differs from the
models), the whole `core/tests.py` suite (65 tests covering registration/age, search, availability,
reminders, confirmation flow, hospital/WhatsApp message, push incl. expired subscriptions, admin, both
languages), rendering of every template, the real browser popups, Google Maps (map load, search, markers,
drag adjustment), real WhatsApp opening, real push delivery, mobile layout.
**I am not claiming any of these pass.**

## 5. Known limitations
- Real-time uses 5-second AJAX polling (no WebSockets); popups need an open tab. Push can notify only
  reminders, not donor requests (by your spec).
- The in-request scheduler is per-process; use the management command in production.
- In-app notification text is stored in the language of whoever triggered it.
- Donor numbers reach any logged-in caller (see decision 2). Consider verifying receivers (OTP) later.
- Eligibility defaults are placeholders until medically validated. Malayalam text needs review.
- Google Places "new" API field names/availability can change; the code falls back to manual entry on errors.
