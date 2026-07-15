"""Shared UI: sidebar, bootstrap, summary cards, filter bar, photo card.

Every page calls require_auth() then render_sidebar(user). The sidebar scopes
the whole app to one project, so adding more projects costs nothing.
"""

import datetime as dt

import streamlit as st

from lib.supa import get_client
from lib import db
from lib import notify
from lib.safety import is_safe_url, escape_html, escape_md


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

        # New project creator, for editors and above. Creates the project in the
        # chosen team and switches to it.
        creatable_teams = [t for t in teams if t.get("_role") in ("owner", "admin", "editor")]
        if creatable_teams:
            with st.popover("＋ New project", use_container_width=True):
                with st.form("new_project_form"):
                    new_name = st.text_input("Project name")
                    if len(creatable_teams) > 1:
                        team_id = st.selectbox(
                            "Team",
                            options=[t["id"] for t in creatable_teams],
                            format_func=lambda tid: next(
                                t["name"] for t in creatable_teams if t["id"] == tid),
                        )
                    else:
                        team_id = creatable_teams[0]["id"]
                    created = st.form_submit_button("Create project")
                if created:
                    if not new_name.strip():
                        st.error("Please enter a project name.")
                    else:
                        try:
                            proj = db.create_project(
                                team_id, new_name.strip(),
                                {"daily_limit": 2, "gps_threshold_km": 5},
                            )
                            st.session_state["project_id"] = proj["id"]
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Could not create project: {exc}")

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


def render_pager(total_pages: int, page_key: str = "dash_page"):
    """A rolling page bar: ‹ 1 … 5 [6] 7 … 120 ›. The current page lives in
    st.session_state[page_key]; clicking a number sets it and reruns. Nothing
    here can select a page past total_pages, so it stays tied to the filter."""
    current = min(max(int(st.session_state.get(page_key, 1)), 1), total_pages)
    if total_pages <= 1:
        return

    win = 1
    nums = {1, total_pages, current}
    for d in range(-win, win + 1):
        p = current + d
        if 1 <= p <= total_pages:
            nums.add(p)
    seq = sorted(nums)

    items, prev = [], 0
    for p in seq:
        if p - prev > 1:
            items.append(None)  # ellipsis gap
        items.append(p)
        prev = p

    labels = ["‹"] + items + ["›"]
    cols = st.columns(len(labels))
    for col, it in zip(cols, labels):
        if it == "‹":
            if col.button("‹", key=f"{page_key}_prev", disabled=current == 1,
                          use_container_width=True):
                st.session_state[page_key] = current - 1
                st.rerun()
        elif it == "›":
            if col.button("›", key=f"{page_key}_next", disabled=current == total_pages,
                          use_container_width=True):
                st.session_state[page_key] = current + 1
                st.rerun()
        elif it is None:
            col.markdown("<div style='text-align:center;color:#888;'>…</div>",
                        unsafe_allow_html=True)
        else:
            if col.button(str(it), key=f"{page_key}_p{it}",
                          type="primary" if it == current else "secondary",
                          use_container_width=True):
                st.session_state[page_key] = it
                st.rerun()


def render_photo_grid(items, reviews, locks, profiles, can_edit, user, project_id,
                      page_key="grid_page", per_page=24, cols=4):
    """A paginated grid of photo cells. Shared by the Dashboard and the pop-out
    panel on the Overview page."""
    if not items:
        st.info("No photos here.")
        return
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = min(max(int(st.session_state.get(page_key, 1)), 1), total_pages)
    st.session_state[page_key] = page
    start = (page - 1) * per_page
    page_items = items[start:start + per_page]
    st.caption(f"Page {page} of {total_pages} · {len(items)} photos")

    for i in range(0, len(page_items), cols):
        row = page_items[i:i + cols]
        cs = st.columns(cols)
        for col, sub in zip(cs, row):
            with col:
                photo_card(sub, reviews.get(sub["id"]), locks.get(sub["id"]),
                           profiles, can_edit, user, project_id)

    if total_pages > 1:
        st.divider()
        render_pager(total_pages, page_key)


# ---------------------------------------------------------------------------
# Summary cards that double as filters
# ---------------------------------------------------------------------------

def summary_cards(stats: dict):
    """Render the summary metrics and the status breakdown. The status cards
    (Approved, Poor Quality, Not Rated, Not Uploaded, To Delete, Duplicates)
    toggle a filter stored in st.session_state['card_filter'] and recompute on
    every rerun, so they update after each review click."""
    active = st.session_state.get("card_filter")

    row1 = st.columns(4)
    row1[0].metric("MCMs", stats["mcm_count"])
    row1[1].metric("Total photos", stats["total"])
    row1[2].metric("Over daily limit", stats["over_limit_mcms"])
    row1[3].metric("Assessed", f"{stats['assessed']} / {stats['total']}")

    st.markdown("**Status** (click to filter)")
    row2 = st.columns(6)
    _filter_card(row2[0], "Approved", stats["approved"], "good", active)
    _filter_card(row2[1], "Poor Quality", stats["poor"], "bad", active)
    _filter_card(row2[2], "Not Rated", stats["not_rated"], "not_rated", active)
    _filter_card(row2[3], "Not Uploaded", stats["not_uploaded"], "not_uploaded", active)
    _filter_card(row2[4], "To Delete", stats["to_delete"], "to_delete", active)
    _filter_card(row2[5], "Duplicates", stats["duplicates"], "duplicate", active)

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

RATING_OPTIONS = ["All", "Not rated", "Rated", "Good", "Bad", "To delete"]


def filter_bar(regions: list, min_date, max_date) -> dict:
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        search = c1.text_input("Search MCM or centre", key="flt_search")
        region = c2.selectbox("Region", options=["All"] + regions, key="flt_region")
        over_only = c3.toggle("Over limit only", key="flt_over")

        c4, c5, c6 = st.columns([2, 2, 1])
        # Rating filter: hide already-rated photos to focus on what is left, or
        # show only a given rating state.
        rating = c4.selectbox("Rating status", options=RATING_OPTIONS, key="flt_rating")
        if min_date and max_date:
            date_range = c5.date_input(
                "Date range",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
                key="flt_dates",
            )
        else:
            date_range = None
        if c6.button("Reset filters", use_container_width=True):
            for k in ("flt_search", "flt_region", "flt_over", "flt_dates", "flt_rating"):
                st.session_state.pop(k, None)
            st.session_state["card_filter"] = None
            st.rerun()

    return {
        "search": search or "",
        "region": None if region == "All" else region,
        "over_only": over_only,
        "date_range": date_range,
        "rating": None if rating == "All" else rating,
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
    url = submission.get("photo_url")

    # Compact badges overlaid on the image, top-left, following the second
    # screenshot. Text is escaped inside badge().
    badges = []
    if flags.get("no_gps"):
        badges.append(badge("No GPS", BADGE_COLORS["no_gps"]))
    if flags.get("gps_far"):
        dist = flags.get("gps_distance_km")
        badges.append(badge(f"GPS>{dist}km" if dist else "GPS far", BADGE_COLORS["gps_far"]))
    if flags.get("over_limit"):
        badges.append(badge(">limit/day", BADGE_COLORS["over_limit"]))
    if flags.get("daily_count"):
        badges.append(badge(f"input {flags['daily_count']}x", BADGE_COLORS["daily"]))
    if submission.get("is_duplicate"):
        badges.append(badge("duplicate", BADGE_COLORS["duplicate"]))
    if lock and lock.get("locked_by") != user.id and _lock_is_fresh(lock):
        badges.append(badge(f"reviewing: {profiles.get(lock['locked_by'], 'someone')}",
                           BADGE_COLORS["lock"]))

    with st.container(border=True):
        if is_safe_url(url):
            safe = escape_html(url)
            st.markdown(
                f'<div style="position:relative;line-height:0;">'
                f'<img class="review-thumb" src="{safe}" loading="lazy" decoding="async" '
                f'style="width:100%;height:auto;border-radius:8px;display:block;" '
                f'alt="submission photo">'
                f'<div style="position:absolute;top:5px;left:5px;display:flex;'
                f'flex-direction:column;align-items:flex-start;gap:3px;">{"".join(badges)}</div>'
                f'<a href="{safe}" target="_blank" rel="noopener" '
                f'style="position:absolute;bottom:6px;right:6px;background:rgba(0,0,0,.6);'
                f'color:#fff;padding:2px 7px;border-radius:6px;font-size:11px;'
                f'text-decoration:none;">open ↗</a></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="height:150px;border-radius:8px;background:rgba(128,128,128,.12);'
                'display:flex;align-items:center;justify-content:center;color:#888;'
                'font-size:13px;">No photo</div>',
                unsafe_allow_html=True,
            )

        # Centre name inside the cell, since photos are grouped by region now.
        centre = submission.get("center_name") or ""
        mcm = submission.get("mcm_id") or ""
        d = submission.get("submission_date") or ""
        cat = submission.get("category") or ""
        if centre:
            st.markdown(f"**{escape_md(centre)}**")
        meta = " · ".join(x for x in [mcm, d] if x)
        st.caption(meta + (f"  \n{escape_md(cat)}" if cat else ""))

        cur_quality = review.get("quality") if review else None
        cur_action = review.get("action") if review else None

        if not can_edit:
            state = ", ".join(x.title() for x in [cur_quality, cur_action] if x) or "not assessed"
            st.caption(state)
            return

        # Direct-action buttons. One click writes immediately and the highlight
        # (primary) shows the current decision.
        r1 = st.columns(2)
        if r1[0].button("✓ Good", key=f"g_{sid}", use_container_width=True,
                        type="primary" if cur_quality == "good" else "secondary"):
            _apply_review(project_id, sid, user, review, profiles, quality="good")
        if r1[1].button("✗ Bad", key=f"b_{sid}", use_container_width=True,
                        type="primary" if cur_quality == "bad" else "secondary"):
            _apply_review(project_id, sid, user, review, profiles, quality="bad")
        r2 = st.columns(2)
        if r2[0].button("Keep", key=f"k_{sid}", use_container_width=True,
                        type="primary" if cur_action == "keep" else "secondary"):
            _apply_review(project_id, sid, user, review, profiles, action="keep")
        if r2[1].button("Delete", key=f"del_{sid}", use_container_width=True,
                        type="primary" if cur_action == "delete" else "secondary"):
            _apply_review(project_id, sid, user, review, profiles, action="delete")

        with st.popover("Note / more", use_container_width=True):
            if review and review.get("reviewer_id"):
                st.caption(f"Last by {profiles.get(review['reviewer_id'], 'someone')} "
                          f"(v{review.get('version', 1)})")
            note = st.text_input("Note", value=(review.get("note") if review else "") or "",
                                 key=f"n_{sid}")
            if st.button("Save note", key=f"sn_{sid}"):
                _apply_review(project_id, sid, user, review, profiles, note=note)
            if st.button("Mark reviewing", key=f"lock_{sid}",
                        help="Let teammates see you are on this photo"):
                try:
                    db.set_lock(project_id, sid, user.id)
                    db.get_review_locks.clear()
                except Exception:
                    pass
                st.rerun()


def _apply_review(project_id, sid, user, review, profiles, quality=None, action=None, note=None):
    """Merge one change (quality, action or note) with the existing review and
    save it with optimistic version checking."""
    cur_q = review.get("quality") if review else None
    cur_a = review.get("action") if review else None
    cur_n = review.get("note") if review else None
    new_q = quality if quality is not None else cur_q
    new_a = action if action is not None else cur_a
    new_n = note if note is not None else cur_n
    seen_version = review.get("version") if review else 0

    ok, conflict = db.save_review(project_id, sid, user.id, new_q, new_a, new_n, seen_version)
    overlay = st.session_state.setdefault("review_overlay", {})
    if ok:
        # Reflect the saved decision locally so the rerun does not have to
        # re-fetch reviews from the database. The dashboard merges this overlay,
        # and drops it once the cached read catches up. This is what makes rating
        # fast: one write, no re-reads.
        overlay[sid] = {
            "submission_id": sid, "project_id": project_id,
            "quality": new_q, "action": new_a, "note": new_n,
            "reviewer_id": user.id, "version": (seen_version or 0) + 1,
        }
        # Only deletions go to the activity feed. Logging every rating was slow
        # and noisy. The reviewer and version still live on the review itself.
        if new_a == "delete":
            db.log_activity(project_id, user.id, "marked_delete", submission_id=sid,
                            details={"quality": new_q, "action": new_a})
            db.get_activity.clear()
        st.rerun()
    else:
        if conflict:
            overlay[sid] = conflict
        who = "another reviewer"
        if conflict and conflict.get("reviewer_id"):
            who = profiles.get(conflict["reviewer_id"], who)
        st.warning(f"{who} updated this photo first. Showing their decision.")
        st.rerun()
