# Build Guide

How to reproduce this project from nothing, and how to bend it to any purpose.
It walks through the four tools it sits on: Claude Code, VS Code and GitHub,
Supabase, and Streamlit Community Cloud. Everything here runs on free tiers.

Pair this with:

- `CLAUDE.md` - the working summary of the architecture, read by Claude Code.
- `TECHNICAL.md` - the full product brief.
- `ROADMAP.md` - the build order and what is done or deferred.

Prose convention in this repo: British English, plain hyphens, no em dashes,
no semicolons.

---

## 0. What you are building

An internal tool for reviewing items (here, field photos) grouped by a category
(here, region and MCM). A reviewer opens a project, sees the items as cells, and
marks each Good or Bad and Keep or Delete. Teams collaborate, with an activity
feed, notifications and edit conflict detection. It is a thin Streamlit front
end over a Supabase (Postgres) database, with row-level security as the access
boundary.

The shape is generic. If you can express your work as "a list of items, each
with a link and some fields, that a human sorts into buckets", this skeleton
fits. Section 11 covers how to re-point it.

---

## 1. Accounts and tools

Create these accounts (all have a free tier):

1. **GitHub** - holds the code, and Streamlit deploys from it.
2. **Supabase** - the database and auth. supabase.com.
3. **Streamlit Community Cloud** - hosting. share.streamlit.io, sign in with
   GitHub.
4. **Anthropic** - for Claude Code. console.anthropic.com or a Claude
   subscription that includes Claude Code.

Install these locally:

1. **Python 3.11 or later**. On Windows, Anaconda is a common choice. Note that
   the `streamlit` command may not be on your PATH with Anaconda, in which case
   you run it through the interpreter, for example
   `C:\Users\YOU\anaconda3\python.exe -m streamlit run app.py`.
2. **Git**. git-scm.com.
3. **VS Code**. code.visualstudio.com. Add the Python extension.
4. **Node.js** (includes npm and npx). nodejs.org. Needed for the Claude Code
   CLI and for optional tools like impeccable.
5. **Claude Code**. Install with `npm install -g @anthropic-ai/claude-code`,
   then run `claude` inside your project folder. There is also a VS Code
   extension that runs Claude Code in the integrated terminal. Check
   docs.claude.com for the current install command if this changes.

---

## 2. Get the code

You have two starting points.

### Path A, clone this repo (fastest)

```
git clone https://github.com/Marcoroons/Cimory_Photo_Dashboard.git
cd Cimory_Photo_Dashboard
```

The optional design-audit submodule is not needed to run the app. If you want
it: `git submodule update --init`.

### Path B, rebuild from the brief with Claude Code

Start an empty folder, put `TECHNICAL.md` and `CLAUDE.md` in it, open Claude
Code, and ask it to scaffold the project following those files. This is how the
project was built. It is slower but teaches you the codebase. See section 10.

---

## 3. Set up Supabase

1. Sign in to supabase.com and create a new project. Choose a region near your
   users. Wait for it to finish provisioning.
2. Open the **SQL editor**. Open `supabase/migrations/0001_schema.sql` from the
   repo, copy the whole file, paste it in, and run it. This creates every table,
   the row-level security policies, the helper functions and the RPCs. It is
   idempotent, so running it again is safe.
   - Migrations `0002` and `0003` are deltas already folded into `0001`. You
     only run them if you applied an older `0001` and want just the change.
3. Open **Authentication, Providers** (or Sign In / Providers). Make sure the
   **Email** provider is enabled and new sign ups are allowed.
4. Open **Authentication, Settings** and turn **OFF "Confirm email"**. This is
   what makes sign up seamless. The shared admin code is the sign-up gate
   instead of email confirmation.
5. Open **Project Settings, API**. Copy two values:
   - the **Project URL**, like `https://abcd1234.supabase.co`
   - the **anon public** key (NOT the service role key, which must never leave
     the dashboard).

Security note. The app only ever uses the anon public key. Row-level security is
the real boundary. Never put the service role key in the repo or in Streamlit.

---

## 4. Configure secrets locally

Streamlit reads secrets from `.streamlit/secrets.toml`, which is gitignored.

```
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml`:

```
SUPABASE_URL = "https://YOUR-PROJECT.supabase.co"
SUPABASE_ANON_KEY = "your-anon-public-key"
ADMIN_SIGNUP_CODE = "cimory123"   # optional, this is the default
```

`ADMIN_SIGNUP_CODE` is the shared code new users type once to create an account.
Change it to rotate access. If you leave it out, the app defaults to `cimory123`.

---

## 5. Run it locally

```
pip install -r requirements.txt
streamlit run app.py
```

If `streamlit` is not found (common with Anaconda on Windows), run it through the
interpreter:

```
C:\Users\YOU\anaconda3\python.exe -m pip install -r requirements.txt
C:\Users\YOU\anaconda3\python.exe -m streamlit run app.py
```

A browser tab opens. You should see the login page. If you see "Supabase is not
configured", your `secrets.toml` is missing or wrong.

---

## 6. Push to GitHub

If you cloned this repo you already have a remote. If you started fresh:

1. Create a new empty repo on GitHub.
2. In your project folder:

```
git init -b main
git add -A
git commit -m "Initial commit"
git remote add origin https://github.com/YOU/YOUR-REPO.git
git push -u origin main
```

Confirm `.streamlit/secrets.toml` is NOT in the push. It is gitignored, so it
should not be. Only `secrets.toml.example` is committed.

---

## 7. Deploy to Streamlit Community Cloud

1. Go to share.streamlit.io and sign in with GitHub.
2. **New app, from existing repo**. Pick your repo, branch `main`, main file
   path `app.py`.
3. Open **Advanced settings, Secrets** and paste the same two secrets (and the
   admin code if you changed it):

```
SUPABASE_URL = "https://YOUR-PROJECT.supabase.co"
SUPABASE_ANON_KEY = "your-anon-public-key"
ADMIN_SIGNUP_CODE = "cimory123"
```

4. **Deploy**. From now on, every push to `main` redeploys automatically.

---

## 8. First run

1. Open the deployed URL. On the login page, go to **Sign up**.
2. Enter an email, a password and the admin code. Leave "Remember me" off on a
   shared computer.
3. You land in the shared workspace. The first person to sign up becomes the
   owner, everyone after joins as an editor.
4. Go to **Import**, upload a `.csv` or `.xlsx`, let the columns auto-map, and
   run the import.
5. Go to **Overview** to see the KPIs, and click a region to review its photos,
   or go to **Dashboard** to review everything.

---

## 9. The daily loop, once it is live

- **Import** the new file each week. Re-importing an overlapping file is safe, it
  only adds genuinely new rows.
- **Review** on the Dashboard or by drilling in from the Overview. Good, Bad,
  Keep, Delete save on one click.
- **Export** the results as CSV from the Dashboard as a backup.

---

## 10. Using Claude Code to build and change it

This is the part that keeps the tool alive without you writing every line.

1. Open the project folder in VS Code, open a terminal, and run `claude`. Or use
   the Claude Code VS Code extension.
2. Claude reads `CLAUDE.md` on start, which tells it the architecture, the
   conventions and the guardrails. Keep `CLAUDE.md` accurate, it is the single
   most useful file for good results.
3. Ask for changes in plain language. Good prompts are specific and name the
   outcome, for example:
   - "Add a Category filter to the Dashboard filter bar, next to Region."
   - "On the Overview, make the region rows sortable by % Good."
   - "Translate the interface labels to Indonesian."
4. Claude edits files, runs checks, and can commit and push. It should:
   - Byte-compile: `python -m py_compile app.py lib/*.py views/*.py`.
   - Boot test with `streamlit.testing.v1.AppTest.from_file("app.py")` and
     assert `not at.exception`.
   - Test import logic by running `lib.imports.build_rows` against a sample file.
5. Review the change on the deployed app (push triggers a redeploy), then tell
   Claude what to adjust. Work in small steps and confirm each one.

Design work. This repo has the `impeccable` skill linked for Claude Code, so you
can ask for UI critiques and polish and Claude will use it. The link is local,
regenerate it on a new machine with `npx impeccable link --source=.impeccable
--providers=claude`.

---

## 11. Making it fit any purpose

The app is a generic "review items grouped by a category" engine. Nothing about
photos or Indonesia is baked into the core. Here is what to change for a
different job, from smallest to largest.

### 11.1 Labels, branding and theme

- Interface text lives in the `views/*.py` files and `lib/ui.py`. Change the
  strings, or ask Claude to translate them all.
- Theme colours and fonts are in `.streamlit/config.toml`.
- The app title and icons are in `app.py` (`st.set_page_config` and the
  `st.Page` entries).

### 11.2 Thresholds and per-project settings

- Editable in the app on **Project Settings**, stored as JSON in
  `projects.config`: the daily limit, the GPS distance threshold, the region and
  category lists, and per-MCM reference coordinates. No code change needed.

### 11.3 The source columns and mapping

- The import auto-detects columns in `lib/imports.py`, in `CANONICAL_FIELDS` and
  the `_ALIASES` used by `guess_mapping`. Add or rename canonical fields there,
  and add alias words so your headers auto-map.
- Dates default to day first (DD/MM/YYYY). The toggle is on the Import page and
  the parsing is in `_parse_date`.

### 11.4 The flags

- Quality flags are computed in `lib/flags.py` and applied in
  `lib/imports.build_rows`. The GPS far flag compares two coordinates. Swap in
  your own rules here, for example a file size flag or a keyword flag. There is
  no AI, these are plain Python checks.

### 11.5 The statuses and the summary

- The four-way status (Approved, Poor Quality, Not Rated, Not Uploaded) is the
  `_status` function in `views/dashboard.py` and `views/overview.py`, and the
  cards in `lib/ui.summary_cards`. Rename or repartition them to suit your
  workflow, for example Accepted, Rejected, Pending, Missing.

### 11.6 The grouping

- Photos are grouped by region. To group by something else (centre, category,
  date, anything), change the sort key and the `groupby` in `views/dashboard.py`
  and the aggregation in `views/overview.py`.

### 11.7 New pages

- Add a file in `views/`, then add an `st.Page(...)` entry in `app.py`. Read the
  shared context with `from lib.ui import page_context`. Only `app.py` calls
  `set_page_config` and the auth gate.

### 11.8 A different domain entirely

- Because items are referenced by URL and sorted by a human, the same skeleton
  serves document review, form QA, listing moderation, survey triage and so on.
  Keep the tables (`submissions`, `reviews`), rename the fields in your head,
  change the import mapping and the labels. The heavy lifting, auth, teams, RLS,
  idempotent import, collaboration, is domain-agnostic.

### 11.9 The deferred seams

- **AI validation**. `lib/ai.py: suggest_quality` is an empty stub, called
  nowhere. Implement it to pre-fill a suggested Good or Bad, for example by
  calling a vision model, then surface it in `photo_card`.
- **File uploads**. Photos are referenced by URL today. Supabase Storage can
  hold uploaded files if you need that, at the cost of storage limits.
- **Realtime**. Collaboration uses polling. Supabase Realtime can push updates
  if you outgrow polling.

---

## 12. Guardrails to keep

These decisions are load-bearing. Changing them tends to break something.

- **Anon key only, RLS is the boundary.** Never ship the service role key.
- **No server-side image processing.** Images are fetched by the browser from a
  CDN, not by the Streamlit server. Adding Pillow resizing would move that load
  onto the free container and risk running it out of memory.
- **Day-first dates.** The Indonesian source is DD/MM/YYYY. Month-first parsing
  corrupts the data.
- **Idempotent import.** Each row has a deterministic `row_hash`, and insert
  ignores duplicates on `(project_id, row_hash)`. This is what makes re-imports
  safe.
- **Rating is one write.** A Good or Bad click writes once and updates an
  in-memory overlay, it does not re-read the whole list. Keep it that way or
  ratings get slow again.

---

## 13. Troubleshooting

- **Login page says Supabase is not configured.** Secrets are missing. Locally,
  check `.streamlit/secrets.toml`. On Streamlit Cloud, check the app Secrets.
- **Sign up says account created but does not log in.** "Confirm email" is still
  on in Supabase. Turn it off in Authentication settings.
- **Editors cannot create projects or invites (only with RLS on).** Run
  `supabase/migrations/0002_editors_create_projects.sql`.
- **Leaving a team errors (only with RLS on).** Run
  `supabase/migrations/0003_leave_team.sql`.
- **streamlit command not found.** Run through the interpreter, see section 5.
- **Photos do not load.** The image host must be publicly reachable. If the URLs
  need a login or are signed and expiring, the browser cannot fetch them.
- **A brief flash of the login screen on refresh.** The cookie component reads
  asynchronously. `restore_session` waits one rerun for it to hydrate. This is
  expected and quick.
- **git confusion on this machine.** The home directory was once `git init`-ed
  by accident. Always run git from inside the project folder, which has its own
  isolated repo.

---

## 14. File map, at a glance

```
app.py                       router, auth gate, top-level navigation
requirements.txt             Python dependencies
.streamlit/config.toml       theme and server settings
.streamlit/secrets.toml      your Supabase keys (gitignored)
lib/
  supa.py                    Supabase client, secrets, admin code
  auth.py                    login, cookie session, admin-code sign up
  db.py                      cached reads, writes, cache invalidation
  imports.py                 parse, map, flag, dedup, idempotent append
  flags.py                   GPS and daily-count flags, no AI
  notify.py                  unread count and the read marker
  ui.py                      sidebar, cards, filter bar, photo card, pager
  safety.py                  URL, HTML, markdown and CSV safety helpers
  ai.py                      empty AI seam
views/
  overview.py                monitoring KPIs and per-region drill pop-out
  dashboard.py               the review grid, Review Foto per MCM
  import_data.py             the import wizard
  activity.py                activity feed and notifications
  team.py                    members, roles, invites, create and leave teams
  project_settings.py        the project config editor
  handbook.py                the in-app handbook
docs/
  handbook.md                handbook text
  BUILD_GUIDE.md             this file
supabase/migrations/
  0001_schema.sql            full schema, RLS, functions, RPCs
  0002_editors_create_projects.sql
  0003_leave_team.sql
```
