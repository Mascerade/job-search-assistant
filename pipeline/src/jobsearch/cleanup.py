"""Housekeeping that keeps the free tiers comfortable (milestone 5).

Runs in GitHub Actions right after the daily feed:

    uv run jobsearch cleanup --dry-run     # list what would be removed; change nothing
    uv run jobsearch cleanup

Two rules:

1. Old postings you never touched are deleted (with their files):
     - postings that closed 30+ days ago, and
     - Adzuna postings first seen 45+ days ago (Adzuna jobs never get marked closed).
   "Never touched" means the status is still New / Docs ready (or you marked it Not
   interested) and you wrote no notes or contacts. Hand-added jobs are never deleted.

2. Files for jobs you're done with are deleted: rejected / withdrawn / not interested for
   60+ days. The resume and cover letter files go; the job and its history stay.

Supabase's free tier has 1 GB of file storage, and the website loads at most 1,000 jobs,
so this keeps both well under their limits.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel

from .daily import AGGREGATOR_ATS

CLOSED_DAYS = 30
AGGREGATOR_DAYS = 45
FILES_DAYS = 60
UNTOUCHED = ("new", "docs_ready", "not_interested")
DONE = ("rejected", "withdrawn", "not_interested")
LIMIT = 500  # per query; anything beyond is picked up by the next day's run
CHUNK = 100  # ids per request (they travel in the URL)


class CleanupJob(BaseModel):
    id: str
    company: str
    title: str
    status: str
    source: str
    notes: str = ""
    contacts: list[Any] = []

    def untouched(self) -> bool:
        return (
            self.status in UNTOUCHED
            and self.source != "manual"
            and not self.notes.strip()
            and not self.contacts
        )


class CleanupDoc(BaseModel):
    id: str
    job_id: str
    docx_path: str | None = None
    pdf_path: str | None = None


class StatusChange(BaseModel):
    job_id: str
    changed_at: datetime


@dataclass
class CleanupPlan:
    stale_jobs: list[CleanupJob] = field(default_factory=list)  # deleted entirely
    done_jobs: list[CleanupJob] = field(default_factory=list)  # files deleted, job kept
    documents: list[CleanupDoc] = field(default_factory=list)  # documents of both groups

    def paths(self) -> list[str]:
        return [p for d in self.documents for p in (d.docx_path, d.pdf_path) if p]

    def done_document_ids(self) -> list[str]:
        done = {j.id for j in self.done_jobs}
        return [d.id for d in self.documents if d.job_id in done]

    def is_empty(self) -> bool:
        return not (self.stale_jobs or self.done_jobs)


def _chunks[T](items: Sequence[T], size: int = CHUNK) -> Iterator[Sequence[T]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


_JOB_COLUMNS = "id, company, title, status, source, notes, contacts"


def pick_done_jobs(
    jobs: list[CleanupJob], last_change: dict[str, datetime], cutoff: datetime
) -> list[CleanupJob]:
    """Done jobs whose status last changed before the cutoff (no history → leave alone)."""
    return [j for j in jobs if (t := last_change.get(j.id)) is not None and t < cutoff]


def plan(now: datetime | None = None) -> CleanupPlan:
    from . import db
    from .db import _rows

    now = now or datetime.now(UTC)
    c = db.client()
    jobs = c.table("jobs")

    closed = _rows(
        jobs.select(_JOB_COLUMNS)
        .lt("closed_at", (now - timedelta(days=CLOSED_DAYS)).isoformat())
        .in_("status", list(UNTOUCHED))
        .limit(LIMIT)
        .execute()
        .data,
        CleanupJob,
    )
    aggregated = _rows(
        jobs.select(_JOB_COLUMNS)
        .in_("source", sorted(AGGREGATOR_ATS))
        .lt("first_seen_at", (now - timedelta(days=AGGREGATOR_DAYS)).isoformat())
        .in_("status", list(UNTOUCHED))
        .limit(LIMIT)
        .execute()
        .data,
        CleanupJob,
    )
    stale = {j.id: j for j in [*closed, *aggregated] if j.untouched()}

    done_candidates = [
        j
        for j in _rows(
            jobs.select(_JOB_COLUMNS).in_("status", list(DONE)).limit(LIMIT).execute().data, CleanupJob
        )
        if j.id not in stale
    ]
    docs_by_job: dict[str, list[CleanupDoc]] = {}
    doc_columns = "id, job_id, docx_path, pdf_path"
    for ids in _chunks([j.id for j in [*stale.values(), *done_candidates]]):
        # A fresh query each time: postgrest filter methods modify the builder in place.
        query = c.table("documents").select(doc_columns).in_("job_id", list(ids))
        for d in _rows(query.execute().data, CleanupDoc):
            docs_by_job.setdefault(d.job_id, []).append(d)

    with_docs = [j for j in done_candidates if j.id in docs_by_job]
    last_change: dict[str, datetime] = {}
    for ids in _chunks([j.id for j in with_docs]):
        for h in _rows(
            c.table("status_history").select("job_id, changed_at").in_("job_id", list(ids)).execute().data,
            StatusChange,
        ):
            if h.job_id not in last_change or h.changed_at > last_change[h.job_id]:
                last_change[h.job_id] = h.changed_at
    done = pick_done_jobs(with_docs, last_change, now - timedelta(days=FILES_DAYS))

    p = CleanupPlan(stale_jobs=list(stale.values()), done_jobs=done)
    p.documents = [d for j in [*p.stale_jobs, *p.done_jobs] for d in docs_by_job.get(j.id, [])]
    return p


def apply(p: CleanupPlan) -> dict[str, int]:
    """Files first: if Storage fails, nothing in the database is touched and tomorrow retries."""
    from . import db

    c = db.client()
    paths = p.paths()
    for chunk in _chunks(paths):
        c.storage.from_(db.DOCUMENTS_BUCKET).remove(list(chunk))
    done_doc_ids = p.done_document_ids()
    for chunk in _chunks(done_doc_ids):
        c.table("documents").delete().in_("id", list(chunk)).execute()
    for chunk in _chunks([j.id for j in p.stale_jobs]):
        c.table("jobs").delete().in_("id", list(chunk)).execute()  # documents, scores, history cascade
    return {
        "jobs_deleted": len(p.stale_jobs),
        "files_deleted": len(paths),
        "documents_deleted": len(p.documents),
        "jobs_with_files_cleared": len(p.done_jobs),
    }


def describe(p: CleanupPlan) -> list[str]:
    lines = [f"Delete {len(p.stale_jobs)} old untouched job(s):"]
    lines += [f"  - {j.title} — {j.company} ({j.status})" for j in p.stale_jobs[:20]]
    if len(p.stale_jobs) > 20:
        lines.append(f"  …and {len(p.stale_jobs) - 20} more")
    lines.append(f"Clear files for {len(p.done_jobs)} finished job(s) (the jobs stay):")
    lines += [f"  - {j.title} — {j.company} ({j.status})" for j in p.done_jobs[:20]]
    lines.append(f"Files to delete from Storage: {len(p.paths())}")
    return lines


def run_cleanup(*, dry_run: bool = False) -> tuple[CleanupPlan, dict[str, int]]:
    from . import db

    p = plan()
    if dry_run or p.is_empty():
        return p, {}
    run_id = db.start_run("cleanup")
    try:
        counts = apply(p)
    except Exception as e:
        db.finish_run(run_id, status="failed", counts={}, error=f"{type(e).__name__}: {e}"[:500])
        raise
    db.finish_run(run_id, status="succeeded", counts=counts)
    return p, counts
