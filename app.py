"""Photo Review dashboard, entry point.

Handles the auth gate and the sidebar project switcher, then shows a short home
overview. The real work lives on the pages in the sidebar.
"""

import streamlit as st

st.set_page_config(page_title="Photo Review dashboard", page_icon="📷", layout="wide")

from lib.auth import require_auth
from lib.ui import render_sidebar
from lib import db

user = require_auth()
project, role, teams = render_sidebar(user)

st.title("Review Foto per MCM")
st.caption(f"Project: {project['name']}")

st.write(
    "Use the sidebar to switch projects and move between pages. Start on the "
    "Dashboard to review photos grouped by MCM, or open Import to load a new "
    "weekly file."
)

# A light home summary so the landing page is not empty.
submissions = db.get_submissions(project["id"])
reviews = db.get_reviews(project["id"])
assessed = sum(1 for r in reviews.values() if r.get("quality"))

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total photos", len(submissions))
c2.metric("MCMs", len({s.get("mcm_id") for s in submissions if s.get("mcm_id")}))
c3.metric("Assessed", f"{assessed} / {len(submissions)}")
c4.metric("Duplicates", sum(1 for s in submissions if s.get("is_duplicate")))

st.divider()
st.subheader("Where to go next")
st.markdown(
    "- **Dashboard** — review photos per MCM, with summary cards that double as filters.\n"
    "- **Import** — load a CSV or Excel file with the mapping wizard.\n"
    "- **Activity** — see who reviewed what, and clear your notifications.\n"
    "- **Team** — manage members, roles and invite codes.\n"
    "- **Project Settings** — regions, categories and the daily and GPS thresholds.\n"
    "- **Handbook** — how the tool works, for new team members."
)

if not submissions:
    st.info("No photos yet. Open the Import page to load your first file.")
