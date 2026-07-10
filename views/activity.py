"""Activity feed and notifications. Opening this page clears the unread bell."""

import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
    _HAS_AUTOREFRESH = True
except Exception:
    _HAS_AUTOREFRESH = False

from lib.ui import page_context
from lib import db, notify
from lib.safety import escape_md

user, project, role, teams = page_context()
project_id = project["id"]

st.title("Activity")
st.caption(f"Project: {project['name']}")

live = st.toggle("Live updates (poll every 25s)", value=False)
if live and _HAS_AUTOREFRESH:
    st_autorefresh(interval=25000, key="activity_poll")
elif live and not _HAS_AUTOREFRESH:
    st.caption("Install streamlit-autorefresh to enable live polling.")

profiles = db.get_profiles_map()
activity = db.get_activity(project_id, limit=200)

# Mark seen so the sidebar bell clears. Do this after reading the feed.
try:
    notify.mark_seen(project_id, user.id)
except Exception:
    pass

ACTION_LABEL = {
    "reviewed": "reviewed a photo",
    "marked_delete": "marked a photo to delete",
    "imported": "imported a file",
    "unlocked": "released a photo",
}

if not activity:
    st.info("No activity yet.")
else:
    for row in activity:
        # who and filename are user-influenced, so escape them for markdown.
        who = escape_md(profiles.get(row.get("actor_id"), "someone"))
        label = ACTION_LABEL.get(row["action"], escape_md(row["action"]))
        when = str(row.get("created_at", ""))[:19].replace("T", " ")
        details = row.get("details") or {}
        extra = ""
        if row["action"] == "imported":
            fname = escape_md(details.get("filename", ""))
            extra = (
                f" — {int(details.get('inserted', 0) or 0)} new, "
                f"{int(details.get('skipped', 0) or 0)} skipped, {fname}"
            )
        elif details.get("quality") or details.get("action"):
            bits = [details.get("quality"), details.get("action")]
            extra = " — " + ", ".join(escape_md(b) for b in bits if b)
        st.markdown(f"**{who}** {label}{extra}")
        st.caption(f"{when} UTC")
        st.divider()
