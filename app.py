"""Photo Review dashboard, entry point and router.

Two clearly separate states. When signed out, the login page renders on its own
with no sidebar. When signed in, the sidebar (project switcher plus navigation)
appears and the selected view runs. The pages live in views/ so Streamlit does
not auto-render its own navigation before the auth gate.
"""

import streamlit as st

st.set_page_config(page_title="Photo Review dashboard", page_icon="📷", layout="wide")

from lib.auth import require_auth
from lib.ui import render_sidebar

# Auth gate. If signed out, this renders the login page (no sidebar) and stops.
user = require_auth()

# Signed in: build the sidebar and expose context to the view scripts.
project, role, teams = render_sidebar(user)
st.session_state["_page_ctx"] = (user, project, role, teams)

pages = [
    st.Page("views/overview.py", title="Overview", icon=":material/monitoring:", default=True),
    st.Page("views/dashboard.py", title="Dashboard", icon=":material/photo_library:"),
    st.Page("views/import_data.py", title="Import", icon=":material/upload:"),
    st.Page("views/activity.py", title="Activity", icon=":material/notifications:"),
    st.Page("views/team.py", title="Team", icon=":material/group:"),
    st.Page("views/project_settings.py", title="Project Settings", icon=":material/settings:"),
    st.Page("views/handbook.py", title="Handbook", icon=":material/menu_book:"),
]

# Page navigation as a top bar (like a normal website header) rather than a
# list of tabs in the sidebar. The sidebar keeps the project switcher and
# account. Drilling from Overview into a region still moves you to the next page.
st.navigation(pages, position="top").run()
