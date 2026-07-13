# CLAUDE.md

Guidance for Claude Code and other agents working in this repository. Read this
before making changes. It is the baseline for rebuilding or extending the tool.

## What this is

An internal tool for reviewing field photo submissions grouped by MCM (the field
agent or account identifier) and by region. Reviewers open a project, see photos
as cells grouped under each region, and mark each photo Good or Bad and Keep or
Delete. Teams collaborate on the same project, with an activity feed, unread
notifications and edit conflict detection. The reference page is titled "Review
Foto per MCM".

The full product brief is in TECHNICAL.md. This file is the working summary.

## Stack, all free tier

- App and server: Streamlit multipage app (programmatic router), deployed on
  Streamlit Community Cloud.
- Database and auth: Supabase (Postgres, email and password auth, row-level
  security).
- Language: Python 3.11 or later.
- Key libraries: streamlit, supabase, pandas, openpyxl,
  extra-streamlit-components (cookie session), streamlit-autorefresh,
  python-dateutil.

The app uses the Supabase anon public key only. Row-level security is the real
access boundary. The service role key must never appear in the repo or the
deployed app.

## How to run

Local:

```
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then edit it
streamlit run app.py
```

On this machine streamlit is not on PATH, use the Anaconda interpreter:

```
C:\Users\Acer\anaconda3\python.exe -m streamlit run app.py
```

Secrets (`.streamlit/secrets.toml`, gitignored):

```
SUPABASE_URL = "https://YOUR-PROJECT.supabase.co"
SUPABASE_ANON_KEY = "your-anon-public-key"
ADMIN_SIGNUP_CODE = "cimory123"   # optional, defaults to cimory123
```

Deploy: push to the `main` branch of the GitHub repo, Streamlit Community Cloud
redeploys automatically. Entry point is `app.py`. Set the two Supabase secrets in
the Streamlit Cloud dashboard.

Supabase setup: run the whole of `supabase/migrations/0001_schema.sql` in the SQL
editor, enable the email provider, and turn OFF "Confirm email" so sign up is
seamless.

## Architecture

- `app.py` is the router. It calls `require_auth()` (which renders the login page
  alone, with the sidebar hidden, when signed out) then `render_sidebar()` and
  `st.navigation(...).run()` to run the selected view.
- Pages live in `views/` (not `pages/`), so Streamlit does not auto-render its
  own page nav before the auth gate. Views read `(user, project, role, teams)`
  from `lib.ui.page_context()`. Only `app.py` calls `st.set_page_config` and
  `require_auth`.
- The Streamlit client authenticates as the user (carries their JWT) so Postgres
  row-level security is the real access boundary.

## Library modules (`lib/`)

- `supa.py`: Supabase client factory (one client per session in
  st.session_state), secrets access, `admin_signup_code()`, `set_auth_token()`.
- `auth.py`: cookie session persistence, `restore_session()`, `require_auth()`,
  `sign_in`, `sign_up` (admin-code gated), `sign_out`, the login view.
- `db.py`: typed query helpers, cached reads (`get_submissions`, `get_reviews`,
  `get_activity`, `get_review_locks`, `get_profiles_map`), writes, the review
  version check (`save_review`), activity log, and the cache invalidators.
- `imports.py`: file parsing, `guess_mapping`, `build_rows` (flags, dedup,
  row_hash), `run_import` (idempotent append), mapping templates.
- `flags.py`: `haversine` and `gps_distance_km` for the GPS flags. No AI.
- `notify.py`: unread count and the read marker behind the sidebar bell.
- `ui.py`: `render_sidebar`, `page_context`, `summary_cards`, `filter_bar`,
  `photo_card`, `render_pager`, `badge`. The shared UI.
- `safety.py`: `is_safe_url`, `escape_html`, `escape_md`, `sanitize_csv_value`.
- `ai.py`: `suggest_quality` stub. The AI validation seam, called nowhere.

## Views (`views/`)

Dashboard, Import, Activity, Team, Project Settings, Handbook.

## Data model

Defined in `supabase/migrations/0001_schema.sql`. Every table carries a
`project_id` (directly or through a parent). Access flows from team membership
plus role (viewer, editor, admin, owner). Core tables: profiles, teams,
team_members, invitations, projects, import_templates, ingestion_batches,
submissions, reviews, review_locks, activity_log, project_last_seen.

Security definer RPCs the app relies on: `create_team`, `redeem_invite`,
`join_default_workspace` (seamless shared workspace), plus the RLS helper
functions `is_team_member`, `is_team_admin`, `project_role`.

## Login and onboarding

Sign up takes email, password and the shared admin code (default `cimory123`,
override with `ADMIN_SIGNUP_CODE`). The check runs server side, the browser never
holds the anon key. There is no email confirmation. Everyone who signs up joins
one shared workspace via `join_default_workspace()` (first user owner, the rest
editors), so there is no team-creation step. A 30-day cookie keeps returning
users signed in.

## Dashboard behaviour

- Photos are grouped by REGION, not per MCM. Under each region heading, every
  photo is an individual cell that wraps and fills the row. This avoids wasting a
  full-width row on a one-photo centre. Each cell shows the centre name, MCM id,
  date, overlaid flag badges, an "open" link, and the review buttons.
- Review controls are direct-action buttons (Good, Bad, Keep, Delete). One click
  writes immediately through `_apply_review`, which merges the change with the
  existing review and saves it with an optimistic version check. Note and mark
  reviewing live in a per-cell popover.
- Status partition (drives the summary cards): every submission is exactly one of
  Approved (quality good), Poor Quality (quality bad), Not Rated (has a photo,
  not yet rated) or Not Uploaded (no valid photo link). Not Uploaded takes
  priority. The summary cards double as filters and recompute each rerun, so they
  update after every review click.
- Filters: search, region, over-limit toggle, date range, and a rating status
  select. Summary cards also filter. Pagination is by photo (default 48 per page)
  with a rolling page bar at the bottom (`render_pager`) that is tied to the
  filtered set, clamps, and resets to page 1 when a filter changes.

## Import pipeline specifics

- Source files use Indonesian headers (Nama Region, Nama Center, ID MCM, URL Foto
  Order, Tanggal Transaksi, Order and Customer Latitude and Longitude).
  `guess_mapping` auto-detects them.
- Dates are DD/MM/YYYY. Always parse with dayfirst true. Month first corrupts the
  data. The Import wizard has a "Dates are day first" toggle, default on.
- The photo URL is both the cell text and a hyperlink. `read_upload` also fills
  blank cells from their embedded hyperlink target.
- Missing photos appear as the literal string "(blank)". These count as Not
  Uploaded and are never flagged as duplicates.
- GPS far is measured per row as the distance between the order coordinate and
  the customer coordinate when both are present, else a per-MCM reference from
  project config.
- Idempotent append: each row has a deterministic `row_hash` from project_id,
  mcm_id, region, submission_date and the photo reference. Insert uses upsert with
  ignore-duplicates on `(project_id, row_hash)`. Re-importing the same or an
  overlapping file adds only genuinely new rows. The same photo URL appearing in a
  new row is inserted but flagged `is_duplicate`.
- Row cap of 100k per file. Only .xlsx and .csv are accepted.

## Security posture

- Anon key only, RLS is the boundary. Admin code gate is server side.
- Photos render as browser `<img>` tags, the Streamlit server never fetches them,
  so there is no server-side request forgery and no server bandwidth for images.
  Only http and https URLs are rendered, validated by `is_safe_url`.
- CSV export is run through `sanitize_csv_value` to neutralise spreadsheet formula
  injection. Negative numbers are preserved.
- The activity feed and badges escape user-influenced text (`escape_md`,
  `escape_html`), so filenames and names cannot inject markup.
- Import is capped and limited to .xlsx and .csv. Volumetric denial of service is
  a platform concern (Streamlit Cloud), not the app.

## Performance decisions, do not undo

- Do not add server-side image processing (for example Pillow resize). It would
  turn the zero-cost browser fetch into a heavy server workload, break CDN and
  browser caching, and risk running the free container out of memory. Images are
  small webp on a Cloudflare CDN with a long browser cache.
- Do not add Celery or Redis. There is no heavy CPU work. Good and Bad is a human
  click.
- Free performance levers already in place: lazy `<img loading="lazy">`, a
  per-thumbnail shimmer, photo-based pagination, long read cache TTLs, and
  targeted cache invalidation. A review write clears reviews and activity only,
  not the large submissions list, so rating clicks stay instant. Imports clear
  the submissions cache.

## Conventions

- Prose and comments: no em dashes, no semicolons in prose, plain hyphens,
  British English.
- Keep the stack lean. Prefer a saved mapping template and plain polling over
  heavier machinery. Do not add Realtime, Storage uploads, or AI until needed. The
  seams are noted.
- The AI validation seam is `lib/ai.py: suggest_quality`, called nowhere.

## Gotchas

- Day-first dates, see above.
- The home directory `C:\Users\Acer` was accidentally `git init`-ed once. This
  project has its own isolated repo. Always run git from inside the project
  folder.
- Streamlit reruns the whole script on every interaction. Cache reads, and cache
  the Supabase client per session.
- Columns can nest one level deep. The photo grid columns contain the per-card
  button columns, which is the one allowed level.
- The cookie component reads asynchronously, `restore_session` waits one rerun for
  it to hydrate so returning users are not flashed the login screen.

## Testing without a browser

- Byte-compile: `python -m py_compile app.py lib/*.py views/*.py`.
- Boot test: use `streamlit.testing.v1.AppTest.from_file("app.py")` and assert
  `not at.exception`. With no secrets it renders the login page.
- Logic: import `lib.imports` and run `build_rows` against a sample file to check
  flags, dedup and idempotency.

## Current state and roadmap

See ROADMAP.md.
