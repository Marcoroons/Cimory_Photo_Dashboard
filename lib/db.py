"""Typed query helpers over Supabase.

Reads are cached with a short TTL so the app stays responsive across Streamlit
reruns. Writes clear the relevant caches through invalidate(). Every helper
fetches the session client inside itself so the cache key stays hashable.
"""

import uuid
import datetime as dt

import streamlit as st

from lib.supa import get_client


# ---------------------------------------------------------------------------
# Cache control
# ---------------------------------------------------------------------------

def invalidate_reviews() -> None:
    """After a review write. Submissions do not change when a photo is rated,
    so leave that (large) cache alone and only refresh reviews, the activity
    feed and locks. This is what keeps rating clicks instant."""
    get_reviews.clear()
    get_activity.clear()
    get_review_locks.clear()


def invalidate_submissions() -> None:
    """After an import, when the submission set itself changes."""
    get_submissions.clear()
    get_reviews.clear()
    get_activity.clear()


def invalidate() -> None:
    """Full clear. Kept for callers that want everything refreshed."""
    get_submissions.clear()
    get_reviews.clear()
    get_activity.clear()
    get_review_locks.clear()


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

def ensure_profile(user) -> None:
    """Make sure a profiles row exists for this user (belt and braces beside
    the auth trigger)."""
    client = get_client()
    display = None
    try:
        display = (user.user_metadata or {}).get("display_name")
    except Exception:
        display = None
    payload = {
        "id": user.id,
        "email": getattr(user, "email", None),
        "display_name": display or (getattr(user, "email", "") or "").split("@")[0],
    }
    try:
        client.table("profiles").upsert(payload, on_conflict="id").execute()
    except Exception:
        # The trigger usually handles this. A failure here is not fatal.
        pass


@st.cache_data(ttl=900, show_spinner=False)
def get_profiles_map() -> dict:
    """id -> display_name for showing reviewer and actor names."""
    client = get_client()
    rows = client.table("profiles").select("id, display_name, email").execute().data or []
    out = {}
    for r in rows:
        out[r["id"]] = r.get("display_name") or (r.get("email") or "").split("@")[0]
    return out


# ---------------------------------------------------------------------------
# Teams, projects, membership
# ---------------------------------------------------------------------------

def list_teams() -> list:
    client = get_client()
    return client.table("teams").select("*").order("created_at").execute().data or []


def list_projects() -> list:
    """Every project the user can reach, across all their teams (RLS filters)."""
    client = get_client()
    return (
        client.table("projects")
        .select("*")
        .order("created_at")
        .execute()
        .data
        or []
    )


def get_project(project_id: str) -> dict | None:
    client = get_client()
    rows = client.table("projects").select("*").eq("id", project_id).limit(1).execute().data
    return rows[0] if rows else None


def create_team(name: str) -> str:
    client = get_client()
    res = client.rpc("create_team", {"_name": name}).execute()
    return res.data


def join_default_workspace() -> str:
    """Join (or create, if first) the shared workspace. Returns the project id."""
    client = get_client()
    return client.rpc("join_default_workspace", {}).execute().data


def create_project(team_id: str, name: str, config: dict | None = None) -> dict:
    client = get_client()
    payload = {"team_id": team_id, "name": name, "config": config or {}}
    return client.table("projects").insert(payload).execute().data[0]


def update_project_config(project_id: str, config: dict) -> None:
    client = get_client()
    client.table("projects").update({"config": config}).eq("id", project_id).execute()


def list_team_members(team_id: str) -> list:
    client = get_client()
    return (
        client.table("team_members")
        .select("*")
        .eq("team_id", team_id)
        .order("created_at")
        .execute()
        .data
        or []
    )


def update_member_role(team_id: str, user_id: str, role: str) -> None:
    client = get_client()
    client.table("team_members").update({"role": role}).eq("team_id", team_id).eq(
        "user_id", user_id
    ).execute()


def remove_member(team_id: str, user_id: str) -> None:
    client = get_client()
    client.table("team_members").delete().eq("team_id", team_id).eq(
        "user_id", user_id
    ).execute()


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------

def create_invitation(team_id: str, role: str, email: str | None, created_by: str) -> dict:
    client = get_client()
    code = uuid.uuid4().hex[:10]
    payload = {
        "team_id": team_id,
        "role": role,
        "email": email or None,
        "code": code,
        "created_by": created_by,
    }
    return client.table("invitations").insert(payload).execute().data[0]


def list_invitations(team_id: str) -> list:
    client = get_client()
    return (
        client.table("invitations")
        .select("*")
        .eq("team_id", team_id)
        .order("created_at", desc=True)
        .execute()
        .data
        or []
    )


def revoke_invitation(invitation_id: str) -> None:
    client = get_client()
    client.table("invitations").update({"status": "revoked"}).eq(
        "id", invitation_id
    ).execute()


def redeem_invite(code: str) -> str:
    client = get_client()
    res = client.rpc("redeem_invite", {"_code": code.strip()}).execute()
    return res.data


# ---------------------------------------------------------------------------
# Ingestion batches and submissions
# ---------------------------------------------------------------------------

def get_batch_by_hash(project_id: str, file_hash: str) -> dict | None:
    client = get_client()
    rows = (
        client.table("ingestion_batches")
        .select("*")
        .eq("project_id", project_id)
        .eq("file_hash", file_hash)
        .limit(1)
        .execute()
        .data
    )
    return rows[0] if rows else None


def create_batch(project_id: str, filename: str, file_hash: str, row_count: int, uploaded_by: str) -> dict:
    client = get_client()
    payload = {
        "project_id": project_id,
        "filename": filename,
        "file_hash": file_hash,
        "row_count": row_count,
        "inserted_count": 0,
        "skipped_count": 0,
        "uploaded_by": uploaded_by,
    }
    return client.table("ingestion_batches").insert(payload).execute().data[0]


def update_batch_counts(batch_id: str, inserted: int, skipped: int) -> None:
    client = get_client()
    client.table("ingestion_batches").update(
        {"inserted_count": inserted, "skipped_count": skipped}
    ).eq("id", batch_id).execute()


def insert_submissions(rows: list) -> int:
    """Idempotent append. Returns the number of genuinely new rows."""
    client = get_client()
    inserted = 0
    for chunk_start in range(0, len(rows), 500):
        chunk = rows[chunk_start:chunk_start + 500]
        res = (
            client.table("submissions")
            .upsert(chunk, on_conflict="project_id,row_hash", ignore_duplicates=True)
            .execute()
        )
        inserted += len(res.data or [])
    return inserted


@st.cache_data(ttl=600, show_spinner=False)
def get_submissions(project_id: str) -> list:
    """All submissions for a project. Weekly batches stay small enough to load
    whole and filter in the app."""
    client = get_client()
    out: list = []
    page = 0
    size = 1000
    while True:
        res = (
            client.table("submissions")
            .select("*")
            .eq("project_id", project_id)
            .order("mcm_id")
            .range(page * size, page * size + size - 1)
            .execute()
        )
        batch = res.data or []
        out.extend(batch)
        if len(batch) < size:
            break
        page += 1
    return out


def existing_daily_counts(project_id: str) -> dict:
    """(mcm_id, iso_date) -> count already stored, for the import flags."""
    counts: dict = {}
    for s in get_submissions(project_id):
        key = (s.get("mcm_id"), str(s.get("submission_date")))
        counts[key] = counts.get(key, 0) + 1
    return counts


def existing_photo_urls(project_id: str) -> set:
    return {s.get("photo_url") for s in get_submissions(project_id) if s.get("photo_url")}


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600, show_spinner=False)
def get_reviews(project_id: str) -> dict:
    """submission_id -> review row."""
    client = get_client()
    rows = (
        client.table("reviews").select("*").eq("project_id", project_id).execute().data
        or []
    )
    return {r["submission_id"]: r for r in rows}


def save_review(project_id, submission_id, reviewer_id, quality, action, note, seen_version):
    """Write a review with optimistic version checking.

    Returns (ok, conflict_row). ok is True on success. When ok is False the
    caller reloads and shows conflict_row, which is whatever is stored now.
    """
    client = get_client()
    now = dt.datetime.now(dt.timezone.utc).isoformat()

    if not seen_version:
        # No review seen yet, try a fresh insert. A conflict means someone else
        # got there first between load and submit.
        payload = {
            "submission_id": submission_id,
            "project_id": project_id,
            "quality": quality,
            "action": action,
            "note": note,
            "reviewer_id": reviewer_id,
            "version": 1,
            "updated_at": now,
        }
        try:
            client.table("reviews").insert(payload).execute()
            return True, None
        except Exception:
            current = client.table("reviews").select("*").eq(
                "submission_id", submission_id
            ).limit(1).execute().data
            return False, (current[0] if current else None)

    # Conditional update: only succeeds if the version we saw is still current.
    res = (
        client.table("reviews")
        .update(
            {
                "quality": quality,
                "action": action,
                "note": note,
                "reviewer_id": reviewer_id,
                "version": seen_version + 1,
                "updated_at": now,
            }
        )
        .eq("submission_id", submission_id)
        .eq("version", seen_version)
        .execute()
    )
    if res.data:
        return True, None
    current = client.table("reviews").select("*").eq(
        "submission_id", submission_id
    ).limit(1).execute().data
    return False, (current[0] if current else None)


# ---------------------------------------------------------------------------
# Review locks (optional soft lock)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=45, show_spinner=False)
def get_review_locks(project_id: str) -> dict:
    client = get_client()
    rows = (
        client.table("review_locks").select("*").eq("project_id", project_id).execute().data
        or []
    )
    return {r["submission_id"]: r for r in rows}


def set_lock(project_id: str, submission_id: str, user_id: str) -> None:
    client = get_client()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    client.table("review_locks").upsert(
        {
            "submission_id": submission_id,
            "project_id": project_id,
            "locked_by": user_id,
            "locked_at": now,
        },
        on_conflict="submission_id",
    ).execute()


def clear_lock(submission_id: str) -> None:
    client = get_client()
    client.table("review_locks").delete().eq("submission_id", submission_id).execute()


# ---------------------------------------------------------------------------
# Activity log
# ---------------------------------------------------------------------------

def log_activity(project_id, actor_id, action, submission_id=None, details=None) -> None:
    client = get_client()
    payload = {
        "project_id": project_id,
        "actor_id": actor_id,
        "action": action,
        "submission_id": submission_id,
        "details": details or {},
    }
    try:
        client.table("activity_log").insert(payload).execute()
    except Exception:
        pass


@st.cache_data(ttl=120, show_spinner=False)
def get_activity(project_id: str, limit: int = 200) -> list:
    client = get_client()
    return (
        client.table("activity_log")
        .select("*")
        .eq("project_id", project_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
