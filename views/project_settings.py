"""Project Settings: regions, categories and the daily and GPS thresholds.

Stored as JSON in projects.config. Editable by team admins and owners.
"""

import json

import streamlit as st

from lib.ui import page_context
from lib import db

user, project, role, teams = page_context()
project_id = project["id"]
can_edit = role in ("owner", "admin", "editor")

st.title("Project Settings")
st.caption(f"Project: {project['name']}")

config = project.get("config") or {}

if not can_edit:
    st.info("Only editors, admins and owners can change project settings.")
    st.json(config)
    st.stop()

st.subheader("Thresholds")
daily_limit = st.number_input(
    "Daily limit per MCM (over-limit badge above this)",
    min_value=1, max_value=100, value=int(config.get("daily_limit", 2)),
)
gps_threshold = st.number_input(
    "GPS far threshold (km)",
    min_value=0.1, max_value=1000.0, value=float(config.get("gps_threshold_km", 5)),
)

st.subheader("Labels")
regions_text = st.text_area(
    "Regions (one per line)", value="\n".join(config.get("regions", []))
)
categories_text = st.text_area(
    "Categories (one per line)", value="\n".join(config.get("categories", []))
)

st.subheader("Per-MCM reference coordinates (optional)")
st.caption(
    "JSON of mcm_id to [latitude, longitude]. Used for the GPS far flag when a "
    "distance column is not present in the file."
)
ref_text = st.text_area(
    "mcm_reference JSON",
    value=json.dumps(config.get("mcm_reference", {}), indent=2),
    height=140,
)

if st.button("Save settings", type="primary"):
    try:
        ref = json.loads(ref_text) if ref_text.strip() else {}
    except json.JSONDecodeError as exc:
        st.error(f"Reference coordinates are not valid JSON: {exc}")
        st.stop()
    new_config = {
        "daily_limit": int(daily_limit),
        "gps_threshold_km": float(gps_threshold),
        "regions": [r.strip() for r in regions_text.splitlines() if r.strip()],
        "categories": [c.strip() for c in categories_text.splitlines() if c.strip()],
        "mcm_reference": ref,
    }
    try:
        db.update_project_config(project_id, new_config)
        st.success("Settings saved. Re-import a file to apply new thresholds to flags.")
        st.rerun()
    except Exception as exc:
        st.error(f"Could not save: {exc}")
