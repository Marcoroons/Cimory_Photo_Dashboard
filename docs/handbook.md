## What this tool is for

This is an internal tool for reviewing field photo submissions grouped by MCM,
the field agent or account identifier. You open a project, see photos grouped
per MCM with per-day submission counts and quality flags, and mark each photo
Good or Bad and Keep or Delete. Teams collaborate on the same project, and the
app helps you avoid two people reviewing the same photo.

The core workflow is simple. Import the weekly file, review the photos, export
the results.

## Roles and what each can do

- **viewer** — read everything in the project, but cannot review or import.
- **editor** — everything a viewer can do, plus review photos and import files.
- **admin** — everything an editor can do, plus manage team members and codes.
- **owner** — full control, including deleting the team and its projects.

## Joining a team with an invite code

An admin creates a code on the Team page and shares it with you. You sign in and
redeem the code on the Redeem tab of the login screen, or on the welcome screen
if you are brand new. Redeeming the code adds you to the team with the role the
admin chose.

Admins create codes on the Team page. Pick a role, generate the code, and pass
it on out of band, for example over chat.

## Switching projects

The project switcher is at the top of the sidebar. Everything on every page is
scoped to the selected project, so switching project changes the whole view.
Because the app is scoped this way, adding another tracking project costs
nothing.

## Importing a file

Open the Import page. Upload a CSV or Excel file, or paste a table directly.

1. **Preview** the detected headers and the first rows.
2. **Map columns** to the canonical fields. The required three are the MCM id,
   the submission date, and the photo URL. Region, centre name, captured time,
   category and photo reference are recommended. Latitude, longitude and a GPS
   distance help with the GPS flags.
3. **Save the mapping as a template** if you like, so next week's file maps in
   one click.
4. **Run the import.**

Re-importing an overlapping file is safe. Each row has a deterministic
fingerprint, so rows already present are skipped and only genuinely new rows are
added. Nothing is overwritten and nothing is double counted.

## Reading the badges

- **No GPS** — the row had no latitude or longitude.
- **GPS far** — the photo location is beyond the project distance threshold,
  five kilometres by default.
- **over daily limit** — that MCM submitted more than the daily limit on that
  date, two by default.
- **input Nx** — the purple badge showing how many photos that MCM submitted on
  that date.

Many photos across different dates is normal, because the booth runs daily. Do
not bulk delete just because an MCM has many photos. Look at the per-day counts.

## How to review

Each photo card has Good or Bad for quality, and Keep or Delete for the action.
Add a note if you want. Save the review.

The summary cards at the top double as filters. Click Good, Bad, To delete or
Duplicates to jump straight to that group. The filter bar adds search, region,
date range and an over-limit-only toggle. All filters compose, and the Export
button downloads the current filtered set with the review columns.

## How collaboration works

The Activity page shows who did what, newest first. The bell in the sidebar
shows how many updates you have not seen, and opening the Activity page clears
it.

If two people review the same photo, the app notices. Every review carries a
version. When you save, the app checks the version you started from still
matches. If someone else changed it first, the app tells you who and what they
decided, and reloads rather than overwriting their work. You can also press
Mark reviewing to show teammates you are on a photo.
