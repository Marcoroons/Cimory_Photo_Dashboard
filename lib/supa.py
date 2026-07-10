"""Supabase client factory and secrets access.

The client is created once per browser session and kept in st.session_state so
that each user carries their own JWT. The app only ever uses the anon public
key. Row-level security is the real access boundary, so the service role key is
never referenced here or anywhere in the deployed app.
"""

import streamlit as st
from supabase import create_client, Client


def _secret(name: str):
    """Read a secret without raising if secrets are not configured yet."""
    try:
        return st.secrets[name]
    except Exception:
        return None


def supabase_configured() -> bool:
    return bool(_secret("SUPABASE_URL") and _secret("SUPABASE_ANON_KEY"))


def admin_signup_code() -> str:
    """Shared code a new user must enter once to sign up. Defaults to cimory123."""
    return _secret("ADMIN_SIGNUP_CODE") or "cimory123"


def get_client() -> Client:
    """Return this session's Supabase client, creating it on first use."""
    if "supabase_client" not in st.session_state:
        url = _secret("SUPABASE_URL")
        key = _secret("SUPABASE_ANON_KEY")
        st.session_state.supabase_client = create_client(url, key)
    return st.session_state.supabase_client


def set_auth_token(access_token: str) -> None:
    """Point the PostgREST layer at the user JWT so RLS applies to every query."""
    client = get_client()
    try:
        client.postgrest.auth(access_token)
    except Exception:
        # Older or newer client versions wire this automatically through the
        # auth listener, so a failure here is not fatal.
        pass
