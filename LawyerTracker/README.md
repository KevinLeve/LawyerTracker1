# LawyerTracker v0.1

A desktop app for a single advocate to search and organize publicly
available case information from the eCourts case-status portal
(`services.ecourts.gov.in`), built for academic/capstone demonstration
purposes.

## Setup

```
pip install -r requirements.txt
python main.py
```

Requires Python 3.10+. First launch shows a one-time setup screen
asking your name and the court you primarily practice in - this is a
single-advocate app (no login/accounts), so it's collected once and
used to prefill every search afterward.

## Architecture

```
config/     - single Settings dataclass; every path/constant lives here
utils/      - logging, custom exceptions, flexible date parsing
database/   - SQLite connection management + schema
models/     - Case / SearchRecord / Profile dataclasses + enums
api/        - EcourtsClient (HTTP only) + parser.py (HTML/JSON -> models, no HTTP)
services/   - business logic: location cascade, CAPTCHA, search+auto-save, profile, runtime config
ui/         - CustomTkinter screens (Onboarding, Home, CAPTCHA, Results, My Cases, Settings)
assets/     - static data (states.json)
```

## What talks to eCourts, and how

`api/ecourts_client.py` automates the **public web portal**, the same
way your `full_tracker.py` / `district_test.py` / `captcha_test.py`
scripts did - a `requests.Session`, form posts, the `securimage`
CAPTCHA. Not the reverse-engineered mobile-app API from
`API_INVENTORY.md` - left out on purpose.

### Verified against your captured fixtures

Session bootstrap, CAPTCHA fetch, district/court-complex cascades,
advocate-name search + result parsing (including a party-name-split
fix for the portal's `<br>Vs</br>` separator), case-detail/history
fetch and field extraction. All tested directly against your saved
`district_output.html` / `complex_output.txt` / `result.txt` /
`history_result.html`, not just written and assumed correct.

### Not verified - needs live testing

`search_by_cnr` and `search_by_case_number` in `api/ecourts_client.py`
- no captured request for either in your files, so the endpoint/field
names are a best-effort guess, clearly marked `# UNVERIFIED`. Test
against the live portal's network tab and correct if needed; nothing
downstream (parsing, auto-save, dashboard) needs to change once the
request shape is right.

## What changed based on your feedback

- **Auto-save**: search results are saved automatically (with full
  detail fetched per case - CNR, stage, next hearing date) instead of
  requiring a manual Save click. You review what got saved on the
  Results screen right after searching, and can delete anything that
  isn't yours there or later from My Cases. Saving is an upsert keyed
  on CNR, so re-running a search refreshes existing cases instead of
  duplicating them.
- **Pending / Disposed / Both**: a status selector on the Advocate and
  Case Number tabs, passed straight through to the portal's own
  `case_status` field. The results table itself doesn't say which row
  is which, so for "Both" searches each case's status is *inferred*
  from its detail page instead: presence of "Decision Date" / "Nature
  of Disposal" fields means Disposed, presence of a "Next Hearing Date"
  with neither of those means Pending (see `api/parser.py`,
  `parse_case_history`). This is based on the real structure of your
  captured Pending fixture - I don't have a captured Disposed fixture
  to confirm the exact disposed-page field names against, so treat it
  as a good-faith best effort rather than guaranteed-correct, and
  double check anything tied to a filing deadline. `Case.extra["status_inferred"]`
  records whether inference found a usable signal at all.
- **My Cases dashboard**: a proper table (Case Number / Parties / CNR /
  Stage / Status / Next Hearing / Court / actions), a Dashboard tab
  showing upcoming hearings soonest-first, and a status filter
  (All/Pending/Disposed). Dates in mixed formats ("21-04-2026" and
  "19th June 2026") are both parsed and sorted correctly - see
  `utils/dates.py`.
- **Onboarding**: name + primary court, asked once, stored in a local
  `profile` table, used to prefill (not lock) every search form.

## CAPTCHA handling

Two modes, both requiring an explicit Submit click - nothing auto-submits:

- **Manual** (default): blank box, type what you see, click Submit.
- **OCR-assisted**: runs KevinOCR on the current image and pre-fills
  the box with its guess. Still editable, still requires Submit.

### Setting up OCR-assist

No code editing needed - it's in the app:

1. Open **Settings**.
2. Under "CAPTCHA OCR Assist (KevinOCR)", click **Browse...** and
   select your KevinOCR project folder (the one containing
   `ocr/engine.py` - i.e. `KevinOCR v4/`, not a subfolder of it).
3. Click **Save**. The status line will say "Available" if
   `ocr.engine.OCREngine` loaded successfully.
4. Back on the CAPTCHA screen, switch the segmented control to
   "OCR-assisted" - a "Suggest with KevinOCR" button appears.

KevinOCR itself isn't bundled in this zip (it's your separate ~37MB
project with its own trained model/dataset) - point Settings at
wherever you already keep it. If the path is wrong or `ocr/engine.py`
doesn't import cleanly, the app falls back to manual entry rather than
crashing - check `logs/app.log` for the specific import error.

## Database

SQLite file at `data/lawyertracker.db`:

- `searches` - every search performed (query, location, status filter, timestamp)
- `cases` - every saved case, upserted by CNR, with `next_hearing_iso`
  for sorting and `case_status` for filtering
- `favourites` - reserved for a future starred-cases view (not yet
  exposed in the UI after the My Cases redesign - the delete-based
  workflow covers "which of these are actually mine" for now)
- `profile` - single row: advocate name + default court
- `app_config` - key/value store for runtime settings like the
  KevinOCR path

Schema is created automatically on first run.

## Known open items

- `search_by_cnr` / `search_by_case_number` endpoints need live testing
  (see above).
- "Both" status search infers Pending/Disposed per case from its
  detail page rather than the portal stating it outright (see above) -
  worth confirming against a live Disposed case once you can capture
  one, and adjusting the field names in `parse_case_history` if the
  live page uses different wording than assumed.
- No distinct party-name search tab (eCourts treats it as a separate
  portal section from advocate-name search) - can be added following
  the existing Home-screen tab pattern.

