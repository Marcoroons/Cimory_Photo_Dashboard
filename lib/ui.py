"""Shared UI: sidebar, bootstrap, summary cards, filter bar, photo card.

Every page calls require_auth() then render_sidebar(user). The sidebar scopes
the whole app to one project, so adding more projects costs nothing.
"""

import datetime as dt

import streamlit as st

from lib.supa import get_client
from lib import db
from lib import notify
from lib.safety import is_safe_url, escape_html


BADGE_COLORS = {
    "no_gps": "#6b7280",
    "gps_far": "#dc2626",
    "over_limit": "#d97706",
    "daily": "#7c3aed",
    "duplicate": "#0ea5e9",
    "lock": "#334155",
}


def badge(text: str, color: str) -> str:
    # text may include a reviewer display name, so escape it before it enters
    # markup rendered with unsafe_allow_html.
    return (
        f"<span style='background:{color};color:#fff;padding:2px 8px;"
        f"border-radius:10px;font-size:11px;margin-right:4px;"
        f"white-space:nowrap;'>{escape_html(text)}</span>"
    )


# ---------------------------------------------------------------------------
# Membership helpers
# ---------------------------------------------------------------------------

def teams_with_role(user) -> list:
    teams = db.list_teams()
    client = get_client()
    mems = (
        client.table("team_members")
        .select("team_id, role")
        .eq("user_id", user.id)
        .execute()
        .data
        or []
    )
    role_by_team = {m["team_id"]: m["role"] for m in mems}
    for t in teams:
        t["_role"] = role_by_team.get(t["id"], "viewer")
    return teams


def project_role(user, project, teams) -> str:
    team = next((t for t in teams if t["id"] == project["team_id"]), None)
    return team["_role"] if team else "viewer"


# ---------------------------------------------------------------------------
# Bootstrap for brand-new users
# ---------------------------------------------------------------------------

def _bootstrap(user, teams):
    st.title("Welcome to the Photo Review dashboard")
    st.write(
        "You are not in a team yet. Create one to get started, or join an "
        "existing team with an invite code."
    )
    left, right = st.columns(2)

    with left:
        st.subheader("Create a team")
        with st.form("bootstrap_team"):
            team_name = st.text_input("Team name")
            project_name = st.text_input("First project name", value="Photo Review")
            submitted = st.form_submit_button("Create team and project")
        if submitted:
            if not team_name.strip():
                st.error("Please enter a team name.")
            else:
                try:
                    team_id = db.create_team(team_name.strip())
                    db.create_project(
                        team_id,
                        project_name.strip() or "Photo Review",
                        {"daily_limit": 2, "gps_threshold_km": 5},
                    )
                    st.success("Team and project created.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not create team: {exc}")

    with right:
        st.subheader("Join with a code")
        with st.form("bootstrap_join"):
            code = st.text_input("Invite code")
            submitted = st.form_submit_button("Join team")
        if submitted:
            try:
                db.redeem_invite(code)
                st.success("Joined the team.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not join: {exc}")
    st.stop()


def _need_project(user, teams):
    st.title("No project yet")
    admin_teams = [t for t in teams if t["_role"] in ("owner", "admin")]
    if not admin_teams:
        st.info(
            "You are in a team but it has no projects. Ask a team admin to "
            "create one."
        )
        st.stop()
    st.write("Create the first project for your team.")
    with st.form("create_first_project"):
        team_id = st.selectbox(
            "Team",
            options=[t["id"] for t in admin_teams],
            format_func=lambda tid: next(t["name"] for t in admin_teams if t["id"] == tid),
        )
        name = st.text_input("Project name", value="Photo Review")
        submitted = st.form_submit_button("Create project")
    if submitted:
        try:
            db.create_project(team_id, name.strip() or "Photo Review",
                              {"daily_limit": 2, "gps_threshold_km": 5})
            st.rerun()
        except Exception as exc:
            st.error(f"Could not create project: {exc}")
    st.stop()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar(user):
    """Ensure setup, render the project switcher and bell, return (project, role, teams)."""
    if not st.session_state.get("_profile_ensured"):
        db.ensure_profile(user)
        st.session_state["_profile_ensured"] = True

    teams = teams_with_role(user)
    if not teams:
        # Seamless onboarding: drop straight into the shared workspace rather
        # than asking the user to create a team. First user creates it.
        try:
            db.join_default_workspace()
            teams = teams_with_role(user)
        except Exception:
            pass
    if not teams:
        _bootstrap(user, teams)

    projects = db.list_projects()
    if not projects:
        _need_project(user, teams)

    project_ids = [p["id"] for p in projects]
    name_by_id = {p["id"]: p["name"] for p in projects}

    current = st.session_state.get("project_id")
    if current not in project_ids:
        current = project_ids[0]
    st.session_state["project_id"] = current

    with st.sidebar:
        st.markdown("### Project")
        selected = st.selectbox(
            "Project",
            options=project_ids,
            index=project_ids.index(current),
            format_func=lambda pid: name_by_id.get(pid, pid),
            label_visibility="collapsed",
        )
        if selected != current:
            st.session_state["project_id"] = selected
            st.rerun()

        project = next(p for p in projects if p["id"] == selected)
        role = project_role(user, project, teams)
        st.caption(f"Your role: {role}")

        try:
            unread = notify.unread_count(selected, user.id)
        except Exception:
            unread = 0
        bell = "🔔" if unread == 0 else f"🔔 {unread}"
        st.markdown(f"**Notifications** {bell}")
        if unread:
            st.caption(f"{unread} new update(s). Open Activity to catch up.")

        st.divider()
        display = (getattr(user, "email", "") or "")
        st.caption(f"Signed in as {display}")
        if st.button("Sign out", use_container_width=True):
            from lib.auth import sign_out
            sign_out()
            st.rerun()

    return project, role, teams


def page_context():
    """Return (user, project, role, teams) set by the router for a view script."""
    ctx = st.session_state.get("_page_ctx")
    if not ctx:
        st.stop()
    return ctx


# ---------------------------------------------------------------------------
# Summary cards that double as filters
# ---------------------------------------------------------------------------

def summary_cards(stats: dict):
    """Render the summary row. Good, Bad, To-delete and Duplicate toggle a
    filter stored in st.session_state['card_filter']."""
    active = st.session_state.get("card_filter")

    row1 = st.columns(4)
    row1[0].metric("MCMs", stats["mcm_count"])
    row1[1].metric("Total photos", stats["total"])
    row1[2].metric("Over daily limit", stats["over_limit_mcms"])
    row1[3].metric("Assessed", f"{stats['assessed']} / {stats['total']}")

    row2 = st.columns(4)
    _filter_card(row2[0], "Good", stats["good"], "good", active)
    _filter_card(row2[1], "Bad", stats["bad"], "bad", active)
    _filter_card(row2[2], "To delete", stats["to_delete"], "to_delete", active)
    _filter_card(row2[3], "Duplicates", stats["duplicates"], "duplicate", active)

    if active:
        st.caption(f"Filtering by: {active}. Click the card again to clear.")


def _filter_card(col, label, value, key, active):
    is_active = active == key
    prefix = "● " if is_active else ""
    if col.button(f"{prefix}{label}: {value}", key=f"card_{key}", use_container_width=True):
        st.session_state["card_filter"] = None if is_active else key
        st.rerun()


# ---------------------------------------------------------------------------
# Filter bar
# ---------------------------------------------------------------------------

def filter_bar(regions: list, min_date, max_date) -> dict:
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        search = c1.text_input("Search MCM or centre", key="flt_search")
        region = c2.selectbox("Region", options=["All"] + regions, key="flt_region")
        over_only = c3.toggle("Over limit only", key="flt_over")

        c4, c5 = st.columns([3, 1])
        if min_date and max_date:
            date_range = c4.date_input(
                "Date range",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
                key="flt_dates",
            )
        else:
            date_range = None
        if c5.button("Reset filters", use_container_width=True):
            for k in ("flt_search", "flt_region", "flt_over", "flt_dates"):
                st.session_state.pop(k, None)
            st.session_state["card_filter"] = None
            st.rerun()

    return {
        "search": search or "",
        "region": None if region == "All" else region,
        "over_only": over_only,
        "date_range": date_range,
        "card": st.session_state.get("card_filter"),
    }


# ---------------------------------------------------------------------------
# Photo card and review controls
# ---------------------------------------------------------------------------

def _lock_is_fresh(lock, minutes=5):
    if not lock:
        return False
    ts = notify._to_dt(lock.get("locked_at"))
    if not ts:
        return False
    age = dt.datetime.now(dt.timezone.utc) - ts
    return age.total_seconds() < minutes * 60


def photo_card(submission, review, lock, profiles, can_edit, user, project_id):
    sid = submission["id"]
    flags = submission.get("flags") or {}

    with st.container(border=True):
        url = submission.get("photo_url")
        # Only render as an image if it is a real http(s) URL. This drops the
        # "(blank)" placeholders and blocks any javascript: or data: value from
        # being treated as an image source or a link. loading="lazy" means the
        # browser only fetches a thumbnail when it scrolls into view, so opening
        # an MCM with dozens of photos does not fire dozens of requests at once,
        # and photos inside a collapsed expander are not fetched at all.
        if is_safe_url(url):
            st.markdown(
                f'<img src="{escape_html(url)}" loading="lazy" decoding="async" '
                f'style="width:100%;height:auto;border-radius:6px;" '
                f'alt="submission photo">',
                unsafe_allow_html=True,
            )
        else:
            st.caption("No photo")

        meta_bits = []
        if submission.get("submission_date"):
            meta_bits.append(str(submission["submission_date"]))
        if submission.get("category"):
            meta_bits.append(submission["category"])
        st.caption(" · ".join(meta_bits) if meta_bits else " ")

        badges = []
        if flags.get("no_gps"):
            badges.append(badge("No GPS", BADGE_COLORS["no_gps"]))
        if flags.get("gps_far"):
            dist = flags.get("gps_distance_km")
            label = f"GPS>{dist}km" if dist else "GPS far"
            badges.append(badge(label, BADGE_COLORS["gps_far"]))
        if flags.get("over_limit"):
            badges.append(badge("over daily limit", BADGE_COLORS["over_limit"]))
        if flags.get("daily_count"):
            badges.append(badge(f"input {flags['daily_count']}x", BADGE_COLORS["daily"]))
        if submission.get("is_duplicate"):
            badges.append(badge("duplicate", BADGE_COLORS["duplicate"]))
        locked_by_other = lock and lock.get("locked_by") != user.id and _lock_is_fresh(lock)
        if locked_by_other:
            who = profiles.get(lock["locked_by"], "someone")
            badges.append(badge(f"reviewing: {who}", BADGE_COLORS["lock"]))
        if badges:
            st.markdown("".join(badges), unsafe_allow_html=True)

        if is_safe_url(url):
            st.link_button("Open full image", url)

        # Current decision.
        cur_quality = review.get("quality") if review else None
        cur_action = review.get("action") if review else None
        if review and review.get("reviewer_id"):
            who = profiles.get(review["reviewer_id"], "someone")
            st.caption(f"Last review by {who} (v{review.get('version', 1)})")

        if not can_edit:
            state = []
            if cur_quality:
                state.append(cur_quality.title())
            if cur_action:
                state.append(cur_action.title())
            st.caption("Decision: " + (", ".join(state) if state else "not assessed"))
            return

        quality = st.radio(
            "Quality",
            options=["good", "bad"],
            index=0 if cur_quality == "good" else 1 if cur_quality == "bad" else None,
            horizontal=True,
            key=f"q_{sid}",
        )
        action = st.radio(
            "Action",
            options=["keep", "delete"],
            index=0 if cur_action == "keep" else 1 if cur_action == "delete" else None,
            horizontal=True,
            key=f"a_{sid}",
        )
        note = st.text_input("Note", value=(review.get("note") if review else "") or "",
                             key=f"n_{sid}")

        cols = st.columns(2)
        if cols[0].button("Save review", key=f"save_{sid}", use_container_width=True):
            _submit_review(project_id, sid, user, quality, action, note, review, profiles)
        if cols[1].button("Mark reviewing", key=f"lock_{sid}", use_container_width=True,
                          help="Let teammates see you are on this photo"):
            try:
                db.set_lock(project_id, sid, user.id)
                db.get_review_locks.clear()
            except Exception:
                pass
            st.rerun()


def _submit_review(project_id, sid, user, quality, action, note, review, profiles):
    if not quality and not action:
        st.warning("Choose Good or Bad, or Keep or Delete, before saving.")
        return
    seen_version = review.get("version") if review else 0
    ok, conflict = db.save_review(
        project_id, sid, user.id, quality, action, note, seen_version
    )
    if ok:
        db.log_activity(
            project_id, user.id,
            "marked_delete" if action == "delete" else "reviewed",
            submission_id=sid,
            details={"quality": quality, "action": action},
        )
        try:
            db.clear_lock(sid)
        except Exception:
            pass
        db.invalidate()
        st.toast("Review saved.")
        st.rerun()
    else:
        who = "another reviewer"
        if conflict and conflict.get("reviewer_id"):
            who = profiles.get(conflict["reviewer_id"], who)
        decided = []
        if conflict:
            if conflict.get("quality"):
                decided.append(conflict["quality"])
            if conflict.get("action"):
                decided.append(conflict["action"])
        st.warning(
            f"{who} reviewed this first ({', '.join(decided) or 'updated'}). "
            "Reloading so you do not overwrite their decision."
        )
        db.invalidate()
        st.rerun()
