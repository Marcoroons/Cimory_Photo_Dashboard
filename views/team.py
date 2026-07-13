"""Team page: members, roles and invite codes."""

import streamlit as st

from lib.ui import page_context
from lib import db

user, project, role, teams = page_context()
team_id = project["team_id"]
team = next((t for t in teams if t["id"] == team_id), None)
is_admin = role in ("owner", "admin")
is_editor_plus = role in ("owner", "admin", "editor")

st.title("Team")
st.caption(f"Team: {team['name'] if team else team_id}")

profiles = db.get_profiles_map()

# ---------------------------------------------------------------------------
# Members. Changing roles and removing members stays with owners and admins.
# This is the "editors cannot kick anyone out" line, and it also stops an
# editor from promoting themselves. Editors see the list read only.
# ---------------------------------------------------------------------------

st.subheader("Members")
members = db.list_team_members(team_id)
ROLES = ["viewer", "editor", "admin"]

for m in members:
    name = profiles.get(m["user_id"], m["user_id"])
    is_self = m["user_id"] == user.id
    cols = st.columns([3, 2, 1])
    cols[0].write(name + (" (you)" if is_self else ""))
    if is_admin and m["role"] != "owner" and not is_self:
        new_role = cols[1].selectbox(
            "Role", options=ROLES, index=ROLES.index(m["role"]) if m["role"] in ROLES else 0,
            key=f"role_{m['user_id']}", label_visibility="collapsed",
        )
        if new_role != m["role"]:
            db.update_member_role(team_id, m["user_id"], new_role)
            st.rerun()
        if cols[2].button("Remove", key=f"rm_{m['user_id']}"):
            db.remove_member(team_id, m["user_id"])
            st.rerun()
    else:
        cols[1].write(m["role"])

# ---------------------------------------------------------------------------
# Invitations. Editors and above can invite, but only admins can grant admin.
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Invite codes")

if not is_editor_plus:
    st.info("Only editors, admins and owners can create invite codes.")
else:
    invite_roles = ["viewer", "editor", "admin"] if is_admin else ["viewer", "editor"]
    with st.form("invite_form"):
        cols = st.columns([2, 2])
        inv_role = cols[0].selectbox("Role", options=invite_roles)
        inv_email = cols[1].text_input("Email (optional, for your records)")
        submitted = st.form_submit_button("Create invite code")
    if submitted:
        try:
            inv = db.create_invitation(team_id, inv_role, inv_email, user.id)
            st.success(f"Invite code created: {inv['code']}")
        except Exception as exc:
            st.error(f"Could not create invite: {exc}")

    st.write("Existing invitations")
    invites = db.list_invitations(team_id)
    if not invites:
        st.caption("No invitations yet.")
    for inv in invites:
        cols = st.columns([2, 2, 2, 1])
        cols[0].code(inv["code"])
        cols[1].write(inv["role"])
        cols[2].write(inv["status"])
        if inv["status"] == "pending":
            if cols[3].button("Revoke", key=f"rev_{inv['id']}"):
                db.revoke_invitation(inv["id"])
                st.rerun()

st.divider()
st.caption(
    "Most people just sign up with the shared admin code to join the workspace. "
    "Invite codes are for adding someone to this specific team with a set role."
)

# ---------------------------------------------------------------------------
# Team self-service: create your own team, or leave this one.
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Create a new team")
st.caption("You become the owner. A first project is created so it is ready to use.")
with st.form("create_team_form"):
    ct_name = st.text_input("Team name")
    ct_project = st.text_input("First project name", value="Photo Review")
    ct_submit = st.form_submit_button("Create team")
if ct_submit:
    if not ct_name.strip():
        st.error("Please enter a team name.")
    else:
        try:
            new_team = db.create_team(ct_name.strip())
            proj = db.create_project(
                new_team, ct_project.strip() or "Photo Review",
                {"daily_limit": 2, "gps_threshold_km": 5},
            )
            st.session_state["project_id"] = proj["id"]
            st.rerun()
        except Exception as exc:
            st.error(f"Could not create team: {exc}")

st.divider()
st.subheader("Leave this team")
st.caption("You lose access to this team's projects. You can rejoin later with an invite code.")
with st.popover("Leave team"):
    st.write(f"Leave **{team['name'] if team else team_id}**?")
    if st.button("Yes, leave this team", type="primary"):
        try:
            db.leave_team(team_id)
            st.session_state.pop("project_id", None)
            st.rerun()
        except Exception as exc:
            st.error(f"Could not leave: {exc}")
