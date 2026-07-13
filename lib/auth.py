"""Authentication, session persistence and the login gate.

Supabase Auth with email and password. Tokens live in st.session_state for the
run and in a cookie so a full browser refresh keeps the user signed in. Every
page calls require_auth() at the top. The app uses the anon key only, RLS is the
real boundary.
"""

import datetime as dt

import streamlit as st
import extra_streamlit_components as stx

from lib.supa import get_client, set_auth_token, supabase_configured, admin_signup_code
from lib import db

ACCESS_COOKIE = "sb_access_token"
REFRESH_COOKIE = "sb_refresh_token"
REMEMBER_COOKIE = "sb_remember"


# ---------------------------------------------------------------------------
# Cookie manager
# ---------------------------------------------------------------------------

def _cookies():
    if "cookie_manager" not in st.session_state:
        st.session_state.cookie_manager = stx.CookieManager(key="cookie_mgr")
    return st.session_state.cookie_manager


def _persist_tokens(access: str, refresh: str, remember: bool) -> None:
    """Store the session in a cookie. When "remember me" is off the cookie is
    short lived (8 hours, rolling) so the login does not silently persist on the
    device. When on it lasts 30 days. same_site strict blocks cross-site use."""
    cm = _cookies()
    hours = 24 * 30 if remember else 8
    expires = dt.datetime.now() + dt.timedelta(hours=hours)
    try:
        cm.set(ACCESS_COOKIE, access, expires_at=expires, key="set_access", same_site="strict")
        cm.set(REFRESH_COOKIE, refresh, expires_at=expires, key="set_refresh", same_site="strict")
        cm.set(REMEMBER_COOKIE, "1" if remember else "0", expires_at=expires,
               key="set_remember", same_site="strict")
    except Exception:
        pass


def _clear_tokens() -> None:
    cm = _cookies()
    for name, key in ((ACCESS_COOKIE, "del_access"), (REFRESH_COOKIE, "del_refresh"),
                      (REMEMBER_COOKIE, "del_remember")):
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
    cookies = cm.get_all() or {}
    # The cookie component reads asynchronously, so on the very first run of a
    # fresh page load it can report nothing before it has mounted. Give it one
    # rerun to hydrate so a returning user is not flashed the login screen.
    if not cookies and not st.session_state.get("_cookies_checked"):
        st.session_state["_cookies_checked"] = True
        st.rerun()

    access = cookies.get(ACCESS_COOKIE)
    refresh = cookies.get(REFRESH_COOKIE)
    if access and refresh:
        try:
            res = client.auth.set_session(access, refresh)
            if res and res.session:
                _apply_session(res.session)
                if res.session.access_token != access:
                    remember = cookies.get(REMEMBER_COOKIE) == "1"
                    _persist_tokens(res.session.access_token, res.session.refresh_token, remember)
                return res.session.user
        except Exception:
            _clear_tokens()
    return None


# ---------------------------------------------------------------------------
# Sign in, sign up, redeem, sign out
# ---------------------------------------------------------------------------

def sign_in(email: str, password: str, remember: bool = False):
    client = get_client()
    res = client.auth.sign_in_with_password({"email": email, "password": password})
    if not res.session:
        raise RuntimeError("Sign in failed, please check your details.")
    _apply_session(res.session)
    _persist_tokens(res.session.access_token, res.session.refresh_token, remember)
    db.ensure_profile(res.session.user)
    return res.session.user


def sign_up(email: str, password: str, admin_code: str, remember: bool = False):
    """Create an account, gated by the shared admin code.

    The check runs inside the Streamlit server, which holds the anon key, so it
    cannot be bypassed from the browser. Returns (user, has_session). has_session
    is False only when email confirmation is still switched on in Supabase.
    """
    if (admin_code or "").strip() != admin_signup_code():
        raise RuntimeError("Incorrect admin code.")
    client = get_client()
    display_name = (email or "").split("@")[0]
    res = client.auth.sign_up(
        {
            "email": email,
            "password": password,
            "options": {"data": {"display_name": display_name}},
        }
    )
    if res.session:
        _apply_session(res.session)
        _persist_tokens(res.session.access_token, res.session.refresh_token, remember)
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
    # The login page stands on its own: no sidebar, content centred in a narrow
    # column so it reads as a separate page from the dashboard.
    st.markdown(
        """<style>
        [data-testid="stSidebar"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="collapsedControl"] { display: none !important; }
        [data-testid="stAppViewContainer"] .block-container {
            max-width: 460px; padding-top: 8vh;
        }
        </style>""",
        unsafe_allow_html=True,
    )
    st.title("Photo Review dashboard")
    st.caption("Sign in to review field photo submissions per MCM.")

    if not supabase_configured():
        st.error(
            "Supabase is not configured yet. Add SUPABASE_URL and "
            "SUPABASE_ANON_KEY to .streamlit/secrets.toml (or the Streamlit "
            "Cloud secrets) and reload."
        )
        st.stop()

    tab_in, tab_up = st.tabs(["Sign in", "Sign up"])

    with tab_in:
        with st.form("sign_in_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            remember = st.checkbox("Remember me on this device (30 days)", value=False)
            submitted = st.form_submit_button("Sign in")
        if submitted:
            try:
                sign_in(email, password, remember)
                st.rerun()
            except Exception as exc:
                st.error(f"Could not sign in: {exc}")
        st.caption(
            "Leave Remember me off on a shared computer. Signing out clears the "
            "session, and it also expires by itself after a few hours."
        )

    with tab_up:
        st.caption(
            "New here? Enter the admin code once to create your account. You will "
            "not need it again."
        )
        with st.form("sign_up_form"):
            email = st.text_input("Email", key="su_email")
            password = st.text_input("Password", type="password", key="su_pw")
            code = st.text_input("Admin code", type="password", key="su_code")
            remember = st.checkbox("Remember me on this device (30 days)", value=False,
                                  key="su_remember")
            submitted = st.form_submit_button("Create account")
        if submitted:
            try:
                _, has_session = sign_up(email, password, code, remember)
                if has_session:
                    st.success("Account created. Loading your dashboard.")
                    st.rerun()
                else:
                    st.warning(
                        "Account created, but Supabase still has email "
                        "confirmation switched on. Turn off Confirm email in "
                        "Supabase Authentication settings for a seamless flow, "
                        "then sign in."
                    )
            except Exception as exc:
                st.error(f"Could not create account: {exc}")


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
