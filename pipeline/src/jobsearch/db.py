"""Supabase access for the pipeline.

The pipeline uses the secret (service-role) key, which bypasses row-level security.
It must never be shipped to the browser.
"""

from __future__ import annotations

from functools import cache
from typing import Any

from supabase import Client, create_client

from .config import load_config


@cache
def client() -> Client:
    cfg = load_config()
    return create_client(cfg.supabase_url, cfg.supabase_secret_key)


def find_user_id(email: str) -> str | None:
    """Look up an auth user by email (case-insensitive)."""
    page = 1
    while True:
        users = client().auth.admin.list_users(page=page, per_page=200)
        if not users:
            return None
        for user in users:
            if (user.email or "").lower() == email.lower():
                return user.id
        page += 1


def ensure_owner(email: str) -> tuple[str, bool]:
    """Create the single owner account if needed and register it in app_owner.

    Returns (user_id, created).
    """
    user_id = find_user_id(email)
    created = False
    if user_id is None:
        resp = client().auth.admin.create_user({"email": email, "email_confirm": True})
        user_id = resp.user.id
        created = True
    client().table("app_owner").upsert({"user_id": user_id}).execute()
    return user_id, created


def latest_profile() -> dict[str, Any] | None:
    rows = (
        client()
        .table("profile_versions")
        .select("version, data, note, created_at")
        .order("version", desc=True)
        .limit(1)
        .execute()
        .data
    )
    return rows[0] if rows else None


def insert_profile(data: dict[str, Any], note: str) -> int:
    row = client().table("profile_versions").insert({"data": data, "note": note}).execute().data[0]
    return row["version"]
