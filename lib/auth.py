"""Authentication, session persistence and the login gate.

Supabase Auth with email and password. Tokens live in st.session_state for the
run and in a cookie so a full browser refresh keeps the user signed in. Every
page calls require_auth() at the top. The app uses the anon key only, RLS is the
real boundary.
"""

import datetime as dt

import streamlit as st
import extra_streamlit_components as stx

from lib.supa import get_client, set_auth_token, supabase_configured
from lib import db

ACCESS_COOKIE = "sb_access_token"
REFRESH_COOKIE = "sb_refresh_token"


# ---------------------------------------------------------------------------
# Cookie manager
# ---------------------------------------------------------------------------

def _cookies():
    if "cookie_manager" not in st.session_state:
        st.session_state.cookie_manager = stx.CookieManager(key="cookie_mgr")
    return st.session_state.cookie_manager


def _persist_tokens(access: str, refresh: str) -> None:
    cm = _cookies()
    expires = dt.datetime.now() + dt.timedelta(days=30)
    try:
        cm.set(ACCESS_COOKIE, access, expires_at=expires, key="set_access")
        cm.set(REFRESH_COOKIE, refresh, expires_at=expires, key="set_refresh")
    except Exception:
        pass


def _clear_tokens() -> None:
    cm = _cookies()
    for name, key in ((ACCESS_COOKIE, "del_access"), (REFRESH_COOKIE, "del_refresh")):
        try:
            cm.delete(name, key=key)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Session restore
# ---------------------------------------------------------------------------

def _apply_session(session) -> None:
    set_auth_token(session.access_token)
    st.session_state["auth_user"] = session.user
    st.session_state["access_token"] = session.access_token
    st.session_state["refresh_token"] = session.refresh_token


def restore_session():
    """Bring back the signed in user for this run, from state or cookie."""
    client = get_client()

    if st.session_state.get("auth_user") and st.session_state.get("access_token"):
        set_auth_token(st.session_state["access_token"])
        return st.session_state["auth_user"]

    cm = _cookies()
    access = cm.get(ACCESS_COOKIE)
    refresh = cm.get(REFRESH_COOKIE)
    if access and refresh:
        try:
            res = client.auth.set_session(access, refresh)
            if res and res.session:
                _apply_session(res.session)
                if res.session.access_token != access:
                    _persist_tokens(res.session.access_token, res.session.refresh_token)
                return res.session.user
        except Exception:
            _clear_tokens()
    return None


# ---------------------------------------------------------------------------
# Sign in, sign up, redeem, sign out
# ---------------------------------------------------------------------------

def sign_in(email: str, password: str):
    client = get_client()
    res = client.auth.sign_in_with_password({"email": email, "password": password})
    if not res.session:
        raise RuntimeError("Sign in failed, please check your details.")
    _apply_session(res.session)
    _persist_tokens(res.session.access_token, res.session.refresh_token)
    db.ensure_profile(res.session.user)
    return res.session.user


def sign_up(email: str, password: str, display_name: str):
    client = get_client()
    res = client.auth.sign_up(
        {
            "email": email,
            "password": password,
            "options": {"data": {"display_name": display_name}},
        }
    )
    if res.session:
        _apply_session(res.session)
        _persist_tokens(res.session.access_token, res.session.refresh_token)
        db.ensure_profile(res.session.user)
        return res.session.user, True
    # Email confirmation is on, no session yet.
    return res.user, False


def sign_out():
    client = get_client()
    try:
        client.auth.sign_out()
    except Exception:
        pass
    _clear_tokens()
    for key in ("auth_user", "access_token", "refresh_token", "project_id"):
        st.session_state.pop(key, None)


# ---------------------------------------------------------------------------
# Login view
# ---------------------------------------------------------------------------

def _render_login():
    st.title("Photo Review dashboard")
    st.caption("Sign in to review field photo submissions per MCM.")

    if not supabase_configured():
        st.error(
            "Supabase is not configured yet. Add SUPABASE_URL and "
            "SUPABASE_ANON_KEY to .streamlit/secrets.toml (or the Streamlit "
            "Cloud secrets) and reload."
        )
        st.stop()

    tab_in, tab_up, tab_code = st.tabs(["Sign in", "Sign up", "Redeem invite code"])

    with tab_in:
        with st.form("sign_in_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in")
        if submitted:
            try:
                sign_in(email, password)
                st.rerun()
            except Exception as exc:
                st.error(f"Could not sign in: {exc}")

    with tab_up:
        with st.form("sign_up_form"):
            display_name = st.text_input("Display name")
            email = st.text_input("Email", key="su_email")
            password = st.text_input("Password", type="password", key="su_pw")
            submitted = st.form_submit_button("Create account")
        if submitted:
            try:
                _, has_session = sign_up(email, password, display_name)
                if has_session:
                    st.success("Account created. Loading your dashboard.")
                    st.rerun()
                else:
                    st.info(
                        "Account created. Please confirm your email, then sign "
                        "in. If email confirmation is disabled in Supabase you "
                        "can sign in straight away."
                    )
            except Exception as exc:
                st.error(f"Could not create account: {exc}")

    with tab_code:
        st.caption("Sign in and join a team in one step using an invite code.")
        with st.form("redeem_form"):
            email = st.text_input("Email", key="rc_email")
            password = st.text_input("Password", type="password", key="rc_pw")
            code = st.text_input("Invite code")
            submitted = st.form_submit_button("Sign in and join team")
        if submitted:
            try:
                sign_in(email, password)
                db.redeem_invite(code)
                st.success("Joined the team. Loading your dashboard.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not join: {exc}")


def require_auth():
    """Gate a page. Returns the user or renders login and stops."""
    if not supabase_configured():
        _render_login()
        st.stop()
    user = restore_session()
    if not user:
        _render_login()
        st.stop()
    return user
