"""Unread counts and the read marker that drives the sidebar bell.

Polling, not push. The activity feed itself lives in lib/db.get_activity. This
module works out how much of it is unread for the current user and project.
"""

import datetime as dt

from lib.supa import get_client
from lib import db


def _last_seen(project_id: str, user_id: str):
    client = get_client()
    rows = (
        client.table("project_last_seen")
        .select("last_seen_at")
        .eq("project_id", project_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
        .data
    )
    return rows[0]["last_seen_at"] if rows else None


def unread_count(project_id: str, user_id: str) -> int:
    """Activity rows newer than the user's last seen marker for this project."""
    seen = _last_seen(project_id, user_id)
    activity = db.get_activity(project_id, limit=200)
    if not seen:
        return len(activity)
    seen_dt = _to_dt(seen)
    count = 0
    for row in activity:
        created = _to_dt(row.get("created_at"))
        if created and seen_dt and created > seen_dt:
            count += 1
    return count


def mark_seen(project_id: str, user_id: str) -> None:
    client = get_client()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    client.table("project_last_seen").upsert(
        {"project_id": project_id, "user_id": user_id, "last_seen_at": now},
        on_conflict="project_id,user_id",
    ).execute()


def _to_dt(value):
    if not value:
        return None
    try:
        s = str(value).replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(s)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    except (ValueError, TypeError):
        return None
