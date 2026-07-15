# Cimory Photo Review Dashboard

A multi-project photo review and tracking dashboard with team collaboration,
built on a fully free stack: Streamlit, Supabase Postgres and Supabase Auth.

Reviewers open a project, see field photo submissions grouped per MCM with
per-day counts and quality flags, and mark each photo Good or Bad and Keep or
Delete. Teams collaborate on the same project with an activity feed, unread
notifications and edit conflict detection.

**New here? Read [docs/BUILD_GUIDE.md](docs/BUILD_GUIDE.md)** for a full
step-by-step to reproduce this from scratch (Claude Code, VS Code and GitHub,
Supabase, Streamlit) and to adapt it to any purpose.

## Stack

- **App** — Streamlit multipage app, deployable on Streamlit Community Cloud.
- **Database, Auth** — Supabase (Postgres, email and password auth, RLS).
- **Language** — Python 3.11 or later.

The app uses the Supabase anon public key only. Row-level security is the real
access boundary. The service role key never appears in the repo or the deployed
app.

## Project layout

```
app.py                     entry, auth gate, sidebar project switcher
requirements.txt
.streamlit/config.toml     theme
.streamlit/secrets.toml    NOT committed, your Supabase keys
lib/                       supa, auth, db, imports, flags, notify, ui, ai
pages/                     Dashboard, Import, Team, Activity, Project Settings, Handbook
docs/handbook.md           in-app handbook text
supabase/migrations/0001_schema.sql   schema, RLS, triggers, RPCs
```

## Set up Supabase

1. Create a Supabase project.
2. Open the SQL editor and run the whole of `supabase/migrations/0001_schema.sql`.
3. In Authentication settings:
   - Enable the email provider and allow new sign ups (both on by default).
   - **Turn off "Confirm email".** This is what makes sign up seamless, the
     user is signed in straight away with no email step. The shared admin code
     is the sign-up gate instead.
4. Copy the project URL and the anon public key from Project Settings, API.

## Run locally

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then edit it
streamlit run app.py
```

`secrets.toml` holds:

```
SUPABASE_URL = "https://YOUR-PROJECT.supabase.co"
SUPABASE_ANON_KEY = "your-anon-public-key"
```

On Windows with Anaconda, if `streamlit` is not on your PATH, run it through the
interpreter, for example:

```
python -m streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Push this repo to GitHub (already at
   `github.com/Marcoroons/Cimory_Photo_Dashboard`).
2. On Streamlit Community Cloud, create an app from the repo with entry point
   `app.py` on the `main` branch.
3. Add `SUPABASE_URL` and `SUPABASE_ANON_KEY` in the app's Secrets.
4. Deploy, then sign up as the first user, create a team and a project, and
   import a file.

## Sign up and login flow

- **Sign up** takes an email, a password and the shared **admin code**
  (`cimory123` by default, override with `ADMIN_SIGNUP_CODE` in secrets). Enter
  the code once. Everyone who signs up with it lands in the same shared
  workspace automatically, the first person becomes owner and the rest join as
  editors.
- **No email confirmation.** With "Confirm email" turned off in Supabase, sign
  up drops the user straight onto the dashboard.
- **Returning users** are kept signed in by a 30-day cookie session, so future
  visits are seamless with nothing to re-enter.

The admin code gate runs inside the Streamlit server, which holds the anon key,
so it cannot be bypassed from the browser.

## First run

Sign up with the admin code, then open Import to load a file. See the in-app
Handbook, or `docs/handbook.md`, for the full workflow.

## Deferred by design

No AI or vision validation yet. Good and Bad is a human decision. The seam is in
`lib/ai.py` as an empty `suggest_quality` stub, called nowhere, so it is obvious
where a model would slot in later. Supabase Storage uploads and Realtime are
also left as clean future extensions. Photos are referenced by URL, not
uploaded, to stay well inside the free tier.
