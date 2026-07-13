"""Dashboard: Review Foto per MCM.

Summary cards that double as filters, a filter bar, photos grouped by MCM with
per-day counts and quality badges, and the Good, Bad, Keep, Delete controls.
"""

import io

import pandas as pd
import streamlit as st

from lib.ui import page_context, summary_cards, filter_bar, photo_card
from lib import db
from lib.safety import sanitize_csv_value

user, project, role, teams = page_context()
project_id = project["id"]
can_edit = role in ("owner", "admin", "editor")

st.title("Review Foto per MCM")
st.caption(f"Project: {project['name']}")

submissions = db.get_submissions(project_id)
reviews = db.get_reviews(project_id)
locks = db.get_review_locks(project_id)
profiles = db.get_profiles_map()

if not submissions:
    st.info("No photos yet. Open the Import page to load your first file.")
    st.stop()


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

def _review_for(sid):
    return reviews.get(sid)

good = sum(1 for r in reviews.values() if r.get("quality") == "good")
bad = sum(1 for r in reviews.values() if r.get("quality") == "bad")
to_delete = sum(1 for r in reviews.values() if r.get("action") == "delete")
assessed = sum(1 for r in reviews.values() if r.get("quality"))
duplicates = sum(1 for s in submissions if s.get("is_duplicate"))

over_limit_mcms = len({
    s.get("mcm_id")
    for s in submissions
    if (s.get("flags") or {}).get("over_limit")
})

stats = {
    "mcm_count": len({s.get("mcm_id") for s in submissions if s.get("mcm_id")}),
    "total": len(submissions),
    "over_limit_mcms": over_limit_mcms,
    "assessed": assessed,
    "good": good,
    "bad": bad,
    "to_delete": to_delete,
    "duplicates": duplicates,
}

summary_cards(stats)


# ---------------------------------------------------------------------------
# Filter bar
# ---------------------------------------------------------------------------

regions = sorted({s.get("region") for s in submissions if s.get("region")})
dates = [s.get("submission_date") for s in submissions if s.get("submission_date")]
min_date = pd.to_datetime(min(dates)).date() if dates else None
max_date = pd.to_datetime(max(dates)).date() if dates else None

flt = filter_bar(regions, min_date, max_date)


def _passes(s):
    r = reviews.get(s["id"])
    if flt["card"] == "good" and not (r and r.get("quality") == "good"):
        return False
    if flt["card"] == "bad" and not (r and r.get("quality") == "bad"):
        return False
    if flt["card"] == "to_delete" and not (r and r.get("action") == "delete"):
        return False
    if flt["card"] == "duplicate" and not s.get("is_duplicate"):
        return False
    if flt["region"] and s.get("region") != flt["region"]:
        return False
    if flt["over_only"] and not (s.get("flags") or {}).get("over_limit"):
        return False
    if flt["search"]:
        needle = flt["search"].lower()
        hay = f"{s.get('mcm_id') or ''} {s.get('center_name') or ''}".lower()
        if needle not in hay:
            return False
    if flt["date_range"] and isinstance(flt["date_range"], (list, tuple)) and len(flt["date_range"]) == 2:
        start, end = flt["date_range"]
        d = s.get("submission_date")
        if d:
            dd = pd.to_datetime(d).date()
            if dd < start or dd > end:
                return False
    return True


filtered = [s for s in submissions if _passes(s)]
st.caption(f"Showing {len(filtered)} of {len(submissions)} photos.")


# ---------------------------------------------------------------------------
# Export current filtered set
# ---------------------------------------------------------------------------

def _export_df(rows):
    out = []
    for s in rows:
        r = reviews.get(s["id"]) or {}
        flags = s.get("flags") or {}
        out.append({
            "mcm_id": s.get("mcm_id"),
            "center_name": s.get("center_name"),
            "region": s.get("region"),
            "submission_date": s.get("submission_date"),
            "category": s.get("category"),
            "photo_url": s.get("photo_url"),
            "daily_count": flags.get("daily_count"),
            "over_limit": flags.get("over_limit"),
            "no_gps": flags.get("no_gps"),
            "gps_far": flags.get("gps_far"),
            "is_duplicate": s.get("is_duplicate"),
            "quality": r.get("quality"),
            "action": r.get("action"),
            "note": r.get("note"),
            "reviewer": profiles.get(r.get("reviewer_id")) if r.get("reviewer_id") else None,
        })
    frame = pd.DataFrame(out)
    # Neutralise spreadsheet formula injection before the CSV can be reopened
    # in Excel. Numbers, including negative latitudes, are left untouched.
    for c in frame.columns:
        if frame[c].dtype == object:
            frame[c] = frame[c].map(sanitize_csv_value)
    return frame


csv_buf = io.StringIO()
_export_df(filtered).to_csv(csv_buf, index=False)
st.download_button(
    "Export results (CSV)",
    data=csv_buf.getvalue(),
    file_name=f"{project['name']}_review_export.csv",
    mime="text/csv",
)

st.divider()


# ---------------------------------------------------------------------------
# Group by MCM
# ---------------------------------------------------------------------------

by_mcm: dict = {}
for s in filtered:
    by_mcm.setdefault(s.get("mcm_id") or "(no MCM)", []).append(s)

mcm_ids = sorted(by_mcm.keys())

if not mcm_ids:
    st.info("No photos match the current filters.")
    st.stop()

# Keep the page light. Fewer MCMs at once means fewer review widgets and image
# tags in the DOM, which is what keeps a big region from crashing the browser.
PHOTO_CAP = 12
per_page = st.number_input("MCMs per page", min_value=1, max_value=50, value=8, step=1)
total_pages = max(1, (len(mcm_ids) + per_page - 1) // per_page)
page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
start = (page - 1) * per_page
page_mcms = mcm_ids[start:start + per_page]
st.caption(f"Page {page} of {total_pages}. MCMs {start + 1} to {start + len(page_mcms)} of {len(mcm_ids)}.")

for mcm in page_mcms:
    items = by_mcm[mcm]
    dates = [i.get("submission_date") for i in items if i.get("submission_date")]
    distinct_dates = sorted(set(dates))
    day_counts = {}
    for d in dates:
        day_counts[d] = day_counts.get(d, 0) + 1
    max_daily = max(day_counts.values()) if day_counts else 0
    first = items[0]
    header = (
        f"{mcm}  ·  {first.get('center_name') or ''}  ·  {first.get('region') or ''}"
        f"  —  {len(items)} photos, {len(distinct_dates)} days, max {max_daily}x/day"
    )

    with st.expander(header, expanded=(len(page_mcms) == 1)):
        if day_counts:
            day_df = pd.DataFrame(
                sorted(day_counts.items()), columns=["date", "photos"]
            ).set_index("date")
            st.bar_chart(day_df, height=160)

        # Only render the first PHOTO_CAP photos of a busy MCM up front, so an
        # MCM with dozens of photos does not build dozens of review widgets at
        # once. The rest load on demand.
        show_key = f"showall_{mcm}"
        show_all = st.session_state.get(show_key, False)
        display_items = items if show_all else items[:PHOTO_CAP]
        if len(items) > len(display_items):
            st.caption(f"Showing {len(display_items)} of {len(items)} photos.")

        cols_per_row = 3
        for i in range(0, len(display_items), cols_per_row):
            row_items = display_items[i:i + cols_per_row]
            cols = st.columns(cols_per_row)
            for col, sub in zip(cols, row_items):
                with col:
                    photo_card(
                        sub,
                        reviews.get(sub["id"]),
                        locks.get(sub["id"]),
                        profiles,
                        can_edit,
                        user,
                        project_id,
                    )

        if not show_all and len(items) > PHOTO_CAP:
            if st.button(f"Show all {len(items)} photos", key=f"btn_{show_key}"):
                st.session_state[show_key] = True
                st.rerun()
