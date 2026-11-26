"""Cleanup rules (the database queries are exercised against local Supabase separately)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from jobsearch.cleanup import CleanupDoc, CleanupJob, CleanupPlan, pick_done_jobs

NOW = datetime(2026, 11, 26, tzinfo=UTC)


def job(id: str = "j1", **kw: Any) -> CleanupJob:
    base: dict[str, Any] = {
        "id": id,
        "company": "Acme",
        "title": "Analyst",
        "status": "new",
        "source": "greenhouse",
    }
    return CleanupJob.model_validate(base | kw)


@pytest.mark.parametrize("status", ["new", "docs_ready", "not_interested"])
def test_untouched_statuses(status: str) -> None:
    assert job(status=status).untouched()


@pytest.mark.parametrize(
    "kw",
    [
        {"status": "applied"},
        {"status": "interviewing"},
        {"status": "rejected"},
        {"notes": "Talked to Sam at the career fair"},
        {"contacts": [{"name": "Sam"}]},
        {"source": "manual"},  # hand-added jobs are never deleted
    ],
)
def test_anything_you_touched_is_kept(kw: dict[str, Any]) -> None:
    assert not job(**kw).untouched()


def test_whitespace_notes_count_as_empty() -> None:
    assert job(notes="  \n").untouched()


def test_done_jobs_need_an_old_enough_status_change() -> None:
    old, recent, unknown = job("old", status="rejected"), job("recent", status="withdrawn"), job("x")
    last_change = {"old": NOW - timedelta(days=61), "recent": NOW - timedelta(days=10)}
    picked = pick_done_jobs([old, recent, unknown], last_change, NOW - timedelta(days=60))
    assert [j.id for j in picked] == ["old"]


def test_plan_lists_both_files_and_only_done_jobs_document_rows() -> None:
    p = CleanupPlan(
        stale_jobs=[job("stale")],
        done_jobs=[job("done", status="rejected")],
        documents=[
            CleanupDoc(id="d1", job_id="stale", docx_path="stale/r.docx", pdf_path="stale/r.pdf"),
            CleanupDoc(id="d2", job_id="done", docx_path="done/c.docx", pdf_path=None),
        ],
    )
    assert p.paths() == ["stale/r.docx", "stale/r.pdf", "done/c.docx"]
    # Stale jobs' document rows go away with the job (cascade); done jobs keep the job row.
    assert p.done_document_ids() == ["d2"]
    assert not p.is_empty()
    assert CleanupPlan().is_empty()
