"""Dashboard: Review Foto per MCM.

Summary cards that double as filters, a filter bar, photos grouped by MCM with
per-day counts and quality badges, and the Good, Bad, Keep, Delete controls.
"""

import io
from itertools import groupby

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

# Loading feedback while the (cached) reads run. On a cache hit this flashes by,
# on the first load per project it shows the spinner. Images themselves load in
# the browser with a placeholder shimmer, so nothing blocks the server.
with st.spinner("Loading photos…"):
    submissions = db.get_submissions(project_id)
    reviews = db.get_reviews(project_id)
    locks = db.get_review_locks(project_id)
    profiles = db.get_profiles_map()

# Placeholder shimmer shown in each photo slot until the browser paints the
# image. Injected once. rgba keeps it subtle in both light and dark themes.
st.markdown(
    """<style>
    img.review-thumb { background: rgba(128,128,128,0.12); min-height: 150px;
        background-image: linear-gradient(100deg, rgba(128,128,128,0) 30%,
        rgba(200,200,200,0.25) 50%, rgba(128,128,128,0) 70%);
        background-size: 200% 100%; animation: thumbshimmer 1.3s ease-in-out infinite; }
    @keyframes thumbshimmer { 0% { background-position: 150% 0; }
        100% { background-position: -150% 0; } }
    </style>""",
    unsafe_allow_html=True,
)

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
    rating = flt.get("rating")
    if rating:
        has_quality = bool(r and r.get("quality"))
        if rating == "Not rated" and has_quality:
            return False
        if rating == "Rated" and not has_quality:
            return False
        if rating == "Good" and not (r and r.get("quality") == "good"):
            return False
        if rating == "Bad" and not (r and r.get("quality") == "bad"):
            return False
        if rating == "To delete" and not (r and r.get("action") == "delete"):
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
# Group by region, photos as individual cells that wrap and fill the row.
# Paginating by photo (not by MCM) keeps rows full regardless of how many
# photos each centre has, so a one-photo centre no longer wastes a whole row.
# ---------------------------------------------------------------------------

if not filtered:
    st.info("No photos match the current filters.")
    st.stop()


def _sort_key(s):
    return (
        s.get("region") or "~",
        s.get("center_name") or "",
        s.get("mcm_id") or "",
        str(s.get("submission_date") or ""),
    )


ordered = sorted(filtered, key=_sort_key)

COLS = 4
pc1, pc2 = st.columns([1, 1])
per_page = pc1.number_input("Photos per page", min_value=12, max_value=200, value=48, step=12)
total_pages = max(1, (len(ordered) + per_page - 1) // per_page)
page = pc2.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
start = (page - 1) * per_page
page_items = ordered[start:start + per_page]
st.caption(
    f"Page {page} of {total_pages}. Photos {start + 1}-{start + len(page_items)} "
    f"of {len(ordered)}."
)

# Render one wrapping grid per region, headed by the region name. groupby works
# because page_items is a contiguous slice of the region-sorted list.
for region, grp in groupby(page_items, key=lambda s: s.get("region") or "(no region)"):
    grp = list(grp)
    st.markdown(f"### {region}")
    centres = len({g.get("mcm_id") for g in grp})
    st.caption(f"{len(grp)} photos · {centres} centres on this page")
    for i in range(0, len(grp), COLS):
        row = grp[i:i + COLS]
        cols = st.columns(COLS)
        for col, sub in zip(cols, row):
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
