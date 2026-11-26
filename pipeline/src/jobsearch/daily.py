"""The daily job feed: fetch every board, filter, and save.

uv run jobsearch daily --dry-run      # fetch + filter, print results, write nothing
uv run jobsearch daily                # the real thing (what GitHub Actions runs)
"""

from __future__ import annotations

import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, get_args

import yaml

from .config import REPO_DIR
from .filters import Verdict, dedupe_key, detail_verdict, location_verdict, title_verdict
from .http import Http
from .models import Ats, Board, JobRow, Posting, Settings
from .sources import enrich, fetch

if TYPE_CHECKING:
    from .db import RunKind, RunStatus

log = logging.getLogger("jobsearch.daily")

SOURCES_FILE = REPO_DIR / "config" / "sources.yaml"

Where = Literal["all", "cloud", "local"]
# Workday answers cloud servers (GitHub Actions) with persistent 429s but works fine from
# a home connection, so those boards are fetched by the daily job on Kojo's Mac.
LOCAL_ONLY_ATS: frozenset[Ats] = frozenset({"workday"})


def runs_where(board: Board) -> Literal["cloud", "local"]:
    return "local" if board.ats in LOCAL_ONLY_ATS else "cloud"


def load_boards(path: Path = SOURCES_FILE) -> list[Board]:
    data = yaml.safe_load(path.read_text()) or {}
    boards = []
    for ats in get_args(Ats):
        for entry in data.get(ats) or []:
            boards.append(Board(ats=ats, **entry))
    return boards


@dataclass
class BoardResult:
    board: Board
    rows: list[tuple[Posting, Verdict]] = field(default_factory=list)
    seen_ids: list[str] = field(default_factory=list)
    counts: Counter[str] = field(default_factory=Counter)
    error: str | None = None


def process_board(board: Board, settings: Settings, http: Http) -> BoardResult:
    """Fetch one board and run the filters. Never raises; errors are recorded."""
    result = BoardResult(board)
    try:
        listings = fetch(board, http)
    except Exception as e:  # one broken board shouldn't stop the run
        result.error = f"{board.key}: {type(e).__name__}: {e}"[:300]
        return result

    result.seen_ids = [p.source_job_id for p in listings]
    result.counts["fetched"] = len(listings)
    for p in listings:
        tv = title_verdict(p.title, settings)
        if tv.track is None:
            continue  # not a role we track; not counted as "filtered"
        if not tv.keep:
            result.counts["filtered_title"] += 1
            continue
        lv = location_verdict(p, settings)
        if not lv.keep:
            result.counts["filtered_location"] += 1
            continue
        if p.needs_detail:
            try:
                p = enrich(p, board, http)
            except Exception:
                result.counts["detail_errors"] += 1
            else:
                lv = location_verdict(p, settings)  # now with the full location list
                if not lv.keep:
                    result.counts["filtered_location"] += 1
                    continue
        dv = detail_verdict(p, settings)
        result.counts["kept" if dv.keep else "filtered_detail"] += 1
        result.rows.append(
            (
                p,
                Verdict(
                    keep=dv.keep, reason=dv.reason, track=tv.track, remote_type=lv.remote_type, tags=lv.tags
                ),
            )
        )
    return result


def to_row(p: Posting, v: Verdict) -> JobRow:
    lo, hi = p.salary_min, p.salary_max
    if lo is not None and hi is not None and lo > hi:
        lo, hi = None, None
    return {
        "source": p.source,
        "source_job_id": p.source_job_id,
        "source_board": p.board,
        "url": p.url,
        "company": p.company,
        "title": p.title,
        "location": p.location,
        "remote_type": v.remote_type or p.remote_type,
        "employment_type": p.employment_type,
        "salary_min": lo,
        "salary_max": hi,
        "description": p.description,
        "posted_at": p.posted_at.isoformat() if p.posted_at else None,
        "dedupe_key": dedupe_key(p),
        "track": v.track,
        "tags": v.tags,
        "pipeline_state": "new" if v.keep else "filtered_out",
        "filter_reason": v.reason,
    }


@dataclass
class RunSummary:
    counts: Counter[str]
    kept: list[tuple[Posting, Verdict]]
    errors: list[str]


def run_daily(
    *,
    dry_run: bool = False,
    only: list[str] | None = None,
    where: Where = "all",
    workers: int = 4,
    kind: RunKind = "daily",
) -> RunSummary:
    from . import db  # imported lazily so --help works without credentials

    settings = db.load_settings()
    boards = load_boards()
    if only:
        boards = [b for b in boards if b.key in only or b.token in only or b.company in only]
    if where != "all":
        boards = [b for b in boards if runs_where(b) == where]
    run_id = None if dry_run else db.start_run(kind)
    http = Http()
    counts: Counter[str] = Counter()
    errors: list[str] = []
    kept: list[tuple[Posting, Verdict]] = []
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(lambda b: process_board(b, settings, http), boards))

        rows: list[JobRow] = []
        for r in results:
            counts.update(r.counts)
            if r.error:
                errors.append(r.error)
                counts["boards_failed"] += 1
                continue
            counts["boards_ok"] += 1
            rows.extend(to_row(p, v) for p, v in r.rows)
            kept.extend((p, v) for p, v in r.rows if v.keep)

        if run_id is not None:
            counts.update(db.ingest(rows).model_dump())
            for r in results:
                if not r.error:  # only close postings after a complete, successful fetch
                    counts["closed"] += db.close_missing(r.board.key, r.seen_ids)
            status: RunStatus = "failed" if boards and counts["boards_ok"] == 0 else "succeeded"
            db.finish_run(run_id, status=status, counts=dict(counts), error="\n".join(errors) or None)
    except Exception as e:
        if run_id is not None:
            db.finish_run(
                run_id, status="failed", counts=dict(counts), error=f"{type(e).__name__}: {e}"[:1000]
            )
        raise
    finally:
        http.close()
    return RunSummary(counts=counts, kept=kept, errors=errors)
