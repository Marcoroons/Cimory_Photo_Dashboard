# Roadmap

Baseline build order and status for the Photo Review dashboard. Pair this with
CLAUDE.md, which describes how the pieces fit together.

## Build order, for a fresh rebuild

Do it in this sequence so each step is testable before the next.

1. Repo skeleton, requirements.txt, `.streamlit/config.toml`, and `lib/supa.py`
   client factory with session restore.
2. The SQL migration (`supabase/migrations/0001_schema.sql`). Apply it to
   Supabase, enable email auth, turn off Confirm email.
3. Auth: `lib/auth.py`, the login view, `require_auth()`, cookie persistence,
   the admin-code sign-up gate, and `join_default_workspace()` for the shared
   workspace.
4. Router and sidebar: `app.py` with `st.navigation`, `render_sidebar`, and the
   project switcher.
5. Import wizard end to end (`lib/imports.py`, `lib/flags.py`,
   `views/import_data.py`): mapping templates, day-first dates, flags, dedup, and
   idempotent append.
6. Dashboard read side: summary status cards, filter bar, region grouping,
   photo cells, badges.
7. Review write side: Good, Bad, Keep, Delete with the version check and activity
   logging, plus targeted cache invalidation and CSV export.
8. Collaboration: activity feed, unread bell, edit conflict detection, optional
   soft lock and auto-refresh.
9. Team page: members, roles, invitations.
10. Project Settings (config JSON editor) and the Handbook page.

## Status

Done:

- Full scaffold: auth, teams, projects, import, dashboard, review, collaboration,
  settings, handbook.
- Seamless login: admin-code sign-up gate, no email confirmation, one shared
  auto-workspace, 30-day cookie session.
- Separate login page from the dashboard via the `st.navigation` router, sidebar
  only after sign in.
- Real Cimory export handled: Indonesian headers auto-mapped, DD/MM/YYYY dates,
  GPS far measured order to customer coordinate, hyperlink and "(blank)" handling.
- Security hardening: CSV formula-injection guard on export, markup escaping in
  the feed and badges, http(s) URL validation before render, import row cap and
  file-type limit. No server-side image fetch, so no request forgery.
- Dashboard UI: photos grouped by region into a wrapping cell grid, uncropped
  full-aspect lazy thumbnails, direct-action review buttons, per-cell centre
  name.
- Bottom rolling page bar tied to the filtered set.
- Status breakdown: Approved, Poor Quality, Not Rated, Not Uploaded as live
  clickable filter cards. Not Uploaded is a distinct status for photos with no
  link.
- Caching across tab switches and instant rating clicks (targeted invalidation).
- Re-import dedup verified: exact re-import adds nothing, overlapping files add
  only new rows, repeat photo URLs are flagged. Blank photos are no longer
  mistaken for duplicates.
- CLAUDE.md and this roadmap.

## Deferred, seams left in place

- AI or vision validation. No paid inference. `lib/ai.py: suggest_quality` is the
  empty seam, called nowhere. The `reviews` table and the `flags` column leave
  room for a suggested quality later.
- Supabase Storage direct uploads. Photos are referenced by URL for now.
- Supabase Realtime. Polling is used instead, which is simpler and free.
- Row-level security is being finalised by the team. The policies are written in
  the migration. Confirm they are enabled before the tool holds sensitive data.
- Indonesian translation of the interface. The UI is English for now, the labels
  are easy to translate later.

## Known follow-ups

- If reviewers want denser pages without lag, drop the per-cell popover or make
  notes a shared panel. That cuts per-cell widgets by about forty per cent.
- If the media host ever moves behind auth or signed URLs, the browser image
  fetch will break and will need a rethink.
- Consider a small placeholder for images that fail to load, so a dead link shows
  a clear marker rather than the browser default.
