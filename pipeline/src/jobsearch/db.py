"""Supabase access for the pipeline.

The pipeline uses the secret (service-role) key, which bypasses row-level security.
It must never be shipped to the browser.

Supabase returns loosely typed JSON, so every result is validated into a Pydantic
model here; the rest of the code only sees typed values.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import cache
from typing import Any, Literal

from pydantic import BaseModel, TypeAdapter
from supabase import Client, create_client

from .config import load_config
from .models import JobRow, Settings

RunKind = Literal["daily", "on_demand"]
RunStatus = Literal["running", "succeeded", "failed"]


class ProfileVersionRow(BaseModel):
    version: int
    data: dict[str, Any]
    note: str
    created_at: datetime


class _IdRow(BaseModel):
    id: str


class _VersionRow(BaseModel):
    version: int


class _SettingsRow(BaseModel):
    data: Settings


class IngestResult(BaseModel):
    inserted: int = 0
    updated: int = 0
    duplicates: int = 0


def _rows[M: BaseModel](data: object, model: type[M]) -> list[M]:
    return TypeAdapter(list[model]).validate_python(data)  # type: ignore[valid-type]


def _first[M: BaseModel](data: object, model: type[M]) -> M:
    rows = _rows(data, model)
    if not rows:
        raise LookupError(f"expected a {model.__name__} row, got none")
    return rows[0]


@cache
def client() -> Client:
    cfg = load_config()
    return create_client(cfg.supabase_url, cfg.supabase_secret_key)


# ---------------------------------------------------------------------------
# Owner + profile (milestone 1)
# ---------------------------------------------------------------------------


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


def latest_profile() -> ProfileVersionRow | None:
    data = (
        client()
        .table("profile_versions")
        .select("version, data, note, created_at")
        .order("version", desc=True)
        .limit(1)
        .execute()
        .data
    )
    rows = _rows(data, ProfileVersionRow)
    return rows[0] if rows else None


def insert_profile(data: dict[str, Any], note: str) -> int:
    resp = client().table("profile_versions").insert({"data": data, "note": note}).execute()
    return _first(resp.data, _VersionRow).version


# ---------------------------------------------------------------------------
# Job feed (milestone 2)
# ---------------------------------------------------------------------------


def load_settings() -> Settings:
    data = client().table("settings").select("data").eq("id", 1).single().execute().data
    return _SettingsRow.model_validate(data).data


def start_run(kind: RunKind) -> str:
    return _first(client().table("runs").insert({"kind": kind}).execute().data, _IdRow).id


def finish_run(run_id: str, *, status: RunStatus, counts: dict[str, int], error: str | None = None) -> None:
    client().table("runs").update(
        {"status": status, "counts": counts, "error": error, "finished_at": datetime.now(UTC).isoformat()}
    ).eq("id", run_id).execute()


def ingest(rows: list[JobRow], chunk: int = 100) -> IngestResult:
    """Save postings via the ingest_postings database function, in chunks."""
    total = IngestResult()
    for i in range(0, len(rows), chunk):
        resp = client().rpc("ingest_postings", {"postings": rows[i : i + chunk]}).execute()
        part = IngestResult.model_validate(resp.data)
        total.inserted += part.inserted
        total.updated += part.updated
        total.duplicates += part.duplicates
    return total


def close_missing(board_key: str, seen_ids: list[str]) -> int:
    """Mark postings closed that are no longer on `board_key`; returns how many."""
    resp = client().rpc("close_missing_postings", {"board": board_key, "seen_ids": seen_ids}).execute()
    return TypeAdapter(int).validate_python(resp.data)
