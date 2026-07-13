"""Dashboard: Review Foto per MCM.

Summary cards that double as filters, a filter bar, photos grouped by MCM with
per-day counts and quality badges, and the Good, Bad, Keep, Delete controls.
"""

import io
from itertools import groupby

import pandas as pd
import streamlit as st

from lib.ui import page_context, summary_cards, filter_bar, photo_card, render_pager
from lib import db
from lib.safety import sanitize_csv_value, is_safe_url

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

# Merge this session's just-saved ratings (the optimistic overlay) so a click is
# reflected without re-fetching. Drop overlay entries the cached read has caught
# up to, so another reviewer's later change is not masked forever.
_overlay = st.session_state.get("review_overlay", {})
if _overlay:
    _merged = dict(reviews)
    for _sid, _ov in list(_overlay.items()):
        _dbr = reviews.get(_sid)
        if _dbr and _dbr.get("version", 0) >= _ov.get("version", 0):
            _overlay.pop(_sid, None)
        else:
            _merged[_sid] = _ov
    reviews = _merged

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
# Summary statistics. Every submission falls into exactly one status:
# Not Uploaded (no photo link) takes priority; the rest split by quality into
# Approved / Poor Quality / Not Rated. These recompute each rerun, so they
# update live after every review click.
# ---------------------------------------------------------------------------

def _status(s):
    if not is_safe_url(s.get("photo_url")):
        return "not_uploaded"
    q = (reviews.get(s["id"]) or {}).get("quality")
    if q == "good":
        return "approved"
    if q == "bad":
        return "poor"
    return "not_rated"


status_of = {s["id"]: _status(s) for s in submissions}
approved = sum(1 for v in status_of.values() if v == "approved")
poor = sum(1 for v in status_of.values() if v == "poor")
not_rated = sum(1 for v in status_of.values() if v == "not_rated")
not_uploaded = sum(1 for v in status_of.values() if v == "not_uploaded")
to_delete = sum(1 for r in reviews.values() if r.get("action") == "delete")
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
    "assessed": approved + poor,
    "approved": approved,
    "poor": poor,
    "not_rated": not_rated,
    "not_uploaded": not_uploaded,
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


CARD_STATUS = {"good": "approved", "bad": "poor",
               "not_rated": "not_rated", "not_uploaded": "not_uploaded"}


def _passes(s):
    r = reviews.get(s["id"])
    card = flt["card"]
    if card in CARD_STATUS and status_of.get(s["id"]) != CARD_STATUS[card]:
        return False
    if card == "to_delete" and not (r and r.get("action") == "delete"):
        return False
    if card == "duplicate" and not s.get("is_duplicate"):
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

# Reset to page 1 whenever the filter set or the page size changes, and never
# let the page run past the filtered result count. The page number lives in
# session state and is driven by the rolling pager at the bottom of the page.
flt_sig = str((flt.get("search"), flt.get("region"), flt.get("over_only"),
               flt.get("rating"), flt.get("card"), str(flt.get("date_range"))))
per_page = int(st.session_state.get("dash_per_page", 48))
layout_sig = f"{flt_sig}|{per_page}"
if st.session_state.get("dash_layout_sig") != layout_sig:
    st.session_state["dash_layout_sig"] = layout_sig
    st.session_state["dash_page"] = 1

total_pages = max(1, (len(ordered) + per_page - 1) // per_page)
page = min(max(int(st.session_state.get("dash_page", 1)), 1), total_pages)
st.session_state["dash_page"] = page
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

# Bottom controls: page size and the rolling page bar, tied to the filtered set.
st.divider()
bottom = st.columns([1, 3])
with bottom[0]:
    st.number_input("Photos per page", min_value=12, max_value=120, value=48,
                    step=12, key="dash_per_page")
    if per_page > 72:
        st.caption("Higher counts make each click slower to refresh.")
with bottom[1]:
    st.caption(f"Page {page} of {total_pages}")
    render_pager(total_pages, "dash_page")
