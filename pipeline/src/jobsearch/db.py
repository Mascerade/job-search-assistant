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
from .models import JobForScoring, JobRow, Settings

RunKind = Literal["daily", "local", "scoring", "tailoring", "tasks", "on_demand"]
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


def finish_run(
    run_id: str,
    *,
    status: RunStatus,
    counts: dict[str, int],
    error: str | None = None,
    cost_usd: float = 0.0,
) -> None:
    client().table("runs").update(
        {
            "status": status,
            "counts": counts,
            "error": error,
            "cost_usd": round(cost_usd, 5),
            "finished_at": datetime.now(UTC).isoformat(),
        }
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


# ---------------------------------------------------------------------------
# Scoring (milestone 3)
# ---------------------------------------------------------------------------

_SCORING_COLUMNS = (
    "id, company, title, location, remote_type, employment_type, salary_min, salary_max, track, description"
)


def jobs_to_score(limit: int | None = None) -> list[JobForScoring]:
    """Open jobs that passed the filters and haven't been scored yet, newest first."""
    query = (
        client()
        .table("jobs")
        .select(_SCORING_COLUMNS)
        .eq("pipeline_state", "new")
        .is_("fit_score", "null")
        .is_("closed_at", "null")
        .order("first_seen_at", desc=True)
    )
    if limit is not None:
        query = query.limit(limit)
    return _rows(query.execute().data, JobForScoring)


def record_scores(rows: list[dict[str, Any]]) -> int:
    resp = client().rpc("record_scores", {"scores": rows}).execute()
    return TypeAdapter(int).validate_python(resp.data)


class _CostRow(BaseModel):
    cost_usd: float


def month_cost(now: datetime | None = None) -> float:
    """Estimated AI cost logged on runs since the start of this month."""
    now = now or datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    data = client().table("runs").select("cost_usd").gte("started_at", start.isoformat()).execute().data
    return sum(r.cost_usd for r in _rows(data, _CostRow))


# ---------------------------------------------------------------------------
# Evaluation set
# ---------------------------------------------------------------------------


def eval_candidates() -> list[JobForScoring]:
    """Open jobs that passed the hard filters (scored or not), for labeling."""
    data = (
        client()
        .table("jobs")
        .select(_SCORING_COLUMNS)
        .in_("pipeline_state", ["new", "scored", "below_threshold"])
        .is_("closed_at", "null")
        .execute()
        .data
    )
    return _rows(data, JobForScoring)


def jobs_by_ids(ids: list[str]) -> list[JobForScoring]:
    data = client().table("jobs").select(_SCORING_COLUMNS).in_("id", ids).execute().data
    return _rows(data, JobForScoring)


class _UrlRow(BaseModel):
    id: str
    url: str | None


def job_urls(ids: list[str]) -> dict[str, str | None]:
    data = client().table("jobs").select("id, url").in_("id", ids).execute().data
    return {r.id: r.url for r in _rows(data, _UrlRow)}


# ---------------------------------------------------------------------------
# Tailored documents (milestone 4)
# ---------------------------------------------------------------------------

DOCUMENTS_BUCKET = "documents"


class DocumentRow(BaseModel):
    id: str
    kind: Literal["resume", "cover_letter"]
    version: int
    state: str
    content: dict[str, Any]


class DecisionRow(BaseModel):
    document_id: str
    path: str
    decision: Literal["pending", "approved", "rejected"]
    final_text: str | None = None


class JobHeader(BaseModel):
    company: str
    title: str


class TaskRow(BaseModel):
    id: str
    job_id: str | None
    kind: Literal["ingest", "tailor", "render", "regenerate"]


def save_tailored(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    resp = client().rpc("save_tailored", {"job": job_id, "payload": payload}).execute()
    return TypeAdapter(dict[str, Any]).validate_python(resp.data)


def latest_documents(job_id: str) -> dict[str, DocumentRow]:
    data = (
        client()
        .table("documents")
        .select("id, kind, version, state, content")
        .eq("job_id", job_id)
        .order("version", desc=True)
        .execute()
        .data
    )
    latest: dict[str, DocumentRow] = {}
    for row in _rows(data, DocumentRow):
        latest.setdefault(row.kind, row)
    return latest


def suggestion_decisions(document_ids: list[str]) -> list[DecisionRow]:
    data = (
        client()
        .table("suggestions")
        .select("document_id, path, decision, final_text")
        .in_("document_id", document_ids)
        .execute()
        .data
    )
    return _rows(data, DecisionRow)


def job_header(job_id: str) -> JobHeader:
    return JobHeader.model_validate(
        client().table("jobs").select("company, title").eq("id", job_id).single().execute().data
    )


def upload_file(key: str, data: bytes, content_type: str) -> str:
    client().storage.from_(DOCUMENTS_BUCKET).upload(
        key, data, {"content-type": content_type, "upsert": "true"}
    )
    return key


def mark_rendered(document_id: str, *, docx_path: str, pdf_path: str) -> None:
    client().table("documents").update({"state": "final", "docx_path": docx_path, "pdf_path": pdf_path}).eq(
        "id", document_id
    ).execute()


def mark_job_documents_ready(job_id: str) -> None:
    """Pipeline: ready. Application status: "Docs ready", unless Kojo already moved it."""
    client().table("jobs").update({"pipeline_state": "ready"}).eq("id", job_id).execute()
    client().table("jobs").update({"status": "docs_ready"}).eq("id", job_id).eq("status", "new").execute()


def mark_job_error(job_id: str) -> None:
    client().table("jobs").update({"pipeline_state": "error"}).eq("id", job_id).execute()


def jobs_to_tailor(limit: int) -> list[JobForScoring]:
    """Open matches without documents that Kojo hasn't acted on, best fit first."""
    data = (
        client()
        .table("jobs")
        .select(_SCORING_COLUMNS)
        .eq("pipeline_state", "scored")
        .eq("status", "new")
        .is_("closed_at", "null")
        .order("fit_score", desc=True)
        .limit(limit)
        .execute()
        .data
    )
    return _rows(data, JobForScoring)


def queued_tasks(limit: int) -> list[TaskRow]:
    data = (
        client()
        .table("tasks")
        .select("id, job_id, kind")
        .eq("step", "queued")
        .order("created_at")
        .limit(limit)
        .execute()
        .data
    )
    return _rows(data, TaskRow)


def claim_task(task_id: str, step: Literal["writing", "rendering"]) -> bool:
    """Move a task from queued to working; False if another runner already took it."""
    data = (
        client().table("tasks").update({"step": step}).eq("id", task_id).eq("step", "queued").execute().data
    )
    return bool(data)


def update_task(
    task_id: str, step: Literal["writing", "rendering", "ready", "error"], error: str | None = None
) -> None:
    client().table("tasks").update({"step": step, "error": error}).eq("id", task_id).execute()


def unreviewed_jobs() -> list[JobForScoring]:
    """Jobs waiting for approval where Kojo hasn't decided any suggestion yet (safe to redo)."""
    jobs = _rows(
        client().table("jobs").select(_SCORING_COLUMNS).eq("pipeline_state", "needs_approval").execute().data,
        JobForScoring,
    )
    out = []
    for job in jobs:
        docs = latest_documents(job.id)
        decisions = suggestion_decisions([d.id for d in docs.values()]) if docs else []
        if all(d.decision == "pending" for d in decisions):
            out.append(job)
    return out
