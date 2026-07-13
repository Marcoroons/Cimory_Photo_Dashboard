"""Overview: Monitoring and curation summary.

Top-level KPIs and a per-region summary. Selecting a region (or a status
gallery button) drills into the Dashboard filtered to those photos. All figures
recompute each rerun, so they update as photos are rated.
"""

import pandas as pd
import streamlit as st

from lib.ui import page_context
from lib import db
from lib.safety import is_safe_url

user, project, role, teams = page_context()
project_id = project["id"]

submissions = db.get_submissions(project_id)
reviews = db.get_reviews(project_id)

# Same optimistic overlay the Dashboard uses, so the counts match live.
_overlay = st.session_state.get("review_overlay", {})
if _overlay:
    reviews = {**reviews, **{s: o for s, o in _overlay.items()}}

# Period label from the data.
_dates = [pd.to_datetime(s["submission_date"]) for s in submissions if s.get("submission_date")]
if _dates:
    lo, hi = min(_dates), max(_dates)
    period = lo.strftime("%B %Y") if (lo.year, lo.month) == (hi.year, hi.month) \
        else f"{lo.strftime('%b %Y')} - {hi.strftime('%b %Y')}"
else:
    period = ""

st.title(f"Monitoring & Photo Curation{' - ' + period if period else ''}")
st.caption(
    "Live KPIs and per-region figures. Click a region row to drill into its "
    "photos, or use the gallery buttons to jump to a status. Reviews save "
    "automatically."
)

if not submissions:
    st.info("No photos yet. Open the Import page to load your first file.")
    st.stop()


# ---------------------------------------------------------------------------
# Status per submission and aggregate KPIs
# ---------------------------------------------------------------------------

def _status(s):
    if not is_safe_url(s.get("photo_url")):
        return "not_uploaded"
    q = (reviews.get(s["id"]) or {}).get("quality")
    return {"good": "approved", "bad": "poor"}.get(q, "not_rated")


status_of = {s["id"]: _status(s) for s in submissions}
total = len(submissions)
good = sum(1 for v in status_of.values() if v == "approved")
bad = sum(1 for v in status_of.values() if v == "poor")
belum = sum(1 for v in status_of.values() if v == "not_rated")
to_delete = sum(1 for r in reviews.values() if r.get("action") == "delete")
gps_jauh = sum(1 for s in submissions if (s.get("flags") or {}).get("gps_far"))
lewat = len({s.get("mcm_id") for s in submissions if (s.get("flags") or {}).get("over_limit")})


def _kpi(label, value, color):
    return (
        f'<div style="flex:1;min-width:120px;border:1px solid rgba(128,128,128,.2);'
        f'border-radius:12px;padding:12px 16px;background:rgba(128,128,128,.05);">'
        f'<div style="font-size:26px;font-weight:700;color:{color};">{value:,}</div>'
        f'<div style="font-size:11px;color:#888;letter-spacing:.04em;text-transform:uppercase;">'
        f'{label}</div></div>'
    )


cards = "".join([
    _kpi("Total photos", total, "#2563eb"),
    _kpi("Good", good, "#16a34a"),
    _kpi("Bad", bad, "#dc2626"),
    _kpi("Not rated", belum, "#6b7280"),
    _kpi("To delete", to_delete, "#dc2626"),
    _kpi("GPS far >5km", gps_jauh, "#d97706"),
    _kpi("Over 2/day", lewat, "#d97706"),
])
st.markdown(
    f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:6px;">{cards}</div>',
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Gallery drill by status
# ---------------------------------------------------------------------------

def _drill(region=None, card=None):
    st.session_state["flt_region"] = region or "All"
    st.session_state["card_filter"] = card
    st.session_state["dash_page"] = 1
    st.switch_page("views/dashboard.py")


st.write("Open gallery:")
g = st.columns(5)
if g[0].button("Good", use_container_width=True):
    _drill(card="good")
if g[1].button("Bad", use_container_width=True):
    _drill(card="bad")
if g[2].button("Not rated", use_container_width=True):
    _drill(card="not_rated")
if g[3].button("To delete", use_container_width=True):
    _drill(card="to_delete")
if g[4].button("Not uploaded", use_container_width=True):
    _drill(card="not_uploaded")


# ---------------------------------------------------------------------------
# Per-region summary. Selecting a row drills into that region's photos.
# ---------------------------------------------------------------------------

st.subheader("Summary per region")

agg = {}
for s in submissions:
    r = s.get("region") or "(no region)"
    a = agg.setdefault(r, {"Region": r, "Total": 0, "Good": 0, "Bad": 0,
                           "Not rated": 0, "GPS far": 0})
    a["Total"] += 1
    stt = status_of[s["id"]]
    if stt == "approved":
        a["Good"] += 1
    elif stt == "poor":
        a["Bad"] += 1
    elif stt == "not_rated":
        a["Not rated"] += 1
    if (s.get("flags") or {}).get("gps_far"):
        a["GPS far"] += 1

rows = sorted(agg.values(), key=lambda x: x["Total"], reverse=True)
for a in rows:
    rated = a["Good"] + a["Bad"]
    a["% Good"] = round(100 * a["Good"] / rated) if rated else 0

region_df = pd.DataFrame(rows, columns=["Region", "Total", "Good", "Bad",
                                        "Not rated", "GPS far", "% Good"])

event = st.dataframe(
    region_df,
    hide_index=True,
    use_container_width=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={"% Good": st.column_config.NumberColumn(format="%d%%")},
)

if event.selection and event.selection["rows"]:
    picked = region_df.iloc[event.selection["rows"][0]]["Region"]
    _drill(region=picked)

st.caption("Tip: click a region row above to see its photos on the Dashboard.")
