"""Overview: monitoring summary with an in-page pop-out for photos.

Top-level KPIs and a per-region summary. Clicking a region name, or a status
gallery button, pops out that set of photos in a panel on this same page (with
the review controls), rather than switching to the full Dashboard. All figures
recompute each rerun, so they update as photos are rated.
"""

import pandas as pd
import streamlit as st

from lib.ui import page_context, render_photo_grid
from lib import db
from lib.safety import is_safe_url

user, project, role, teams = page_context()
project_id = project["id"]
can_edit = role in ("owner", "admin", "editor")

submissions = db.get_submissions(project_id)
reviews = db.get_reviews(project_id)
locks = db.get_review_locks(project_id)
profiles = db.get_profiles_map()

# Same optimistic overlay the Dashboard uses, so the counts match live.
_overlay = st.session_state.get("review_overlay", {})
if _overlay:
    reviews = {**reviews, **_overlay}

_dates = [pd.to_datetime(s["submission_date"]) for s in submissions if s.get("submission_date")]
if _dates:
    lo, hi = min(_dates), max(_dates)
    period = lo.strftime("%B %Y") if (lo.year, lo.month) == (hi.year, hi.month) \
        else f"{lo.strftime('%b %Y')} - {hi.strftime('%b %Y')}"
else:
    period = ""

st.title(f"Monitoring & Photo Curation{' - ' + period if period else ''}")
st.caption(
    "Live KPIs and per-region figures. Click a region name (or a gallery "
    "button) to pop out those photos here, with the review buttons. Reviews "
    "save automatically."
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
# Drill target and the pop-out panel
# ---------------------------------------------------------------------------

CARD_STATUS = {"good": "approved", "bad": "poor",
               "not_rated": "not_rated", "not_uploaded": "not_uploaded"}
CARD_TITLES = {"good": "Good photos", "bad": "Bad photos", "not_rated": "Not rated",
               "not_uploaded": "Not uploaded", "to_delete": "To delete"}


def _drill(region=None, card=None):
    st.session_state["ov_drill"] = {"region": region, "card": card}
    st.session_state["ov_drill_page"] = 1
    st.rerun()


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


def _matches(s, drill):
    if drill.get("region") and (s.get("region") or "(no region)") != drill["region"]:
        return False
    card = drill.get("card")
    if card:
        if card in CARD_STATUS and status_of.get(s["id"]) != CARD_STATUS[card]:
            return False
        if card == "to_delete" and (reviews.get(s["id"]) or {}).get("action") != "delete":
            return False
    return True


drill = st.session_state.get("ov_drill")
if drill:
    items = [s for s in submissions if _matches(s, drill)]
    title = drill.get("region") or CARD_TITLES.get(drill.get("card"), "Photos")
    with st.container(border=True):
        hc = st.columns([6, 1])
        hc[0].subheader(f"📂 {title}")
        if hc[1].button("✕ Close", use_container_width=True, key="ov_close"):
            st.session_state.pop("ov_drill", None)
            st.session_state.pop("ov_drill_page", None)
            st.rerun()
        render_photo_grid(items, reviews, locks, profiles, can_edit, user, project_id,
                          page_key="ov_drill_page", per_page=24)


# ---------------------------------------------------------------------------
# Per-region summary. Region names are buttons that pop out the photos above.
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

head = st.columns([3, 1, 1, 1, 1, 1, 1])
for lbl, c in zip(["Region", "Total", "Good", "Bad", "Not rated", "GPS far", "% Good"], head):
    c.caption(lbl)
for a in rows:
    rated = a["Good"] + a["Bad"]
    pct = round(100 * a["Good"] / rated) if rated else 0
    c = st.columns([3, 1, 1, 1, 1, 1, 1])
    if c[0].button(a["Region"], key=f"reg_{a['Region']}", type="tertiary",
                   use_container_width=True):
        _drill(region=a["Region"])
    c[1].write(str(a["Total"]))
    c[2].markdown(f":green[{a['Good']}]")
    c[3].markdown(f":red[{a['Bad']}]")
    c[4].write(str(a["Not rated"]))
    c[5].markdown(f":orange[{a['GPS far']}]")
    c[6].write(f"{pct}%")

st.caption("Tip: click a region name to pop out its photos in a panel above.")
