"""Team page: members, roles and invite codes."""

import streamlit as st

from lib.ui import page_context
from lib import db

user, project, role, teams = page_context()
team_id = project["team_id"]
team = next((t for t in teams if t["id"] == team_id), None)
is_admin = role in ("owner", "admin")

st.title("Team")
st.caption(f"Team: {team['name'] if team else team_id}")

profiles = db.get_profiles_map()

# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------

st.subheader("Members")
members = db.list_team_members(team_id)
ROLES = ["viewer", "editor", "admin", "owner"]

for m in members:
    name = profiles.get(m["user_id"], m["user_id"])
    cols = st.columns([3, 2, 1])
    cols[0].write(name)
    if is_admin and m["role"] != "owner" and m["user_id"] != user.id:
        new_role = cols[1].selectbox(
            "Role", options=ROLES, index=ROLES.index(m["role"]),
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
# Invitations
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Invite codes")

if not is_admin:
    st.info("Only team admins and owners can create invite codes.")
else:
    with st.form("invite_form"):
        cols = st.columns([2, 2])
        inv_role = cols[0].selectbox("Role", options=["viewer", "editor", "admin"])
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
    "Share a code out of band. The recipient signs in and redeems it on the "
    "Redeem tab of the login screen, or the bootstrap screen."
)
