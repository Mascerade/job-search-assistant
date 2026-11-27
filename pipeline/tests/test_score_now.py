""" "Score now" on the Today page: the Mac's side of a score task (documents.score_task)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from jobsearch import db, documents, scoring
from jobsearch.db import TaskRow
from jobsearch.llm import AuthExpiredError
from jobsearch.scoring import ScoringSummary


class Calls:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, claimed: bool = True) -> None:
        self.progress: list[dict[str, Any]] = []
        self.final: list[tuple[str, str | None, dict[str, Any] | None]] = []
        monkeypatch.setattr(db, "claim_task", lambda task_id, step: claimed and step == "scoring")
        monkeypatch.setattr(db, "set_task_result", lambda task_id, result: self.progress.append(result))
        monkeypatch.setattr(db, "update_task", self.update)

    def update(self, task_id: str, step: str, error: str | None = None, result: Any = None) -> None:
        self.final.append((step, error, result))


def fake_run(
    summary: ScoringSummary, *, wait: bool = False, raises: Exception | None = None
) -> Callable[..., ScoringSummary]:
    def run(
        *,
        on_wait: Callable[[], None] | None = None,
        on_progress: Callable[[dict[str, int]], None] | None = None,
        **_: Any,
    ) -> ScoringSummary:
        if wait and on_wait:
            on_wait()  # the morning run is scoring
        if raises:
            raise raises
        if on_progress:
            on_progress({"total": summary.total, "scored": 0, "matches": 0, "below": 0, "failed": 0})
        return summary

    return run


def test_score_task_reports_waiting_progress_and_the_result(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = Calls(monkeypatch)
    done = ScoringSummary(total=23, scored=23, kept=9, below=14)
    monkeypatch.setattr(scoring, "run_scoring", fake_run(done, wait=True))

    line = documents.score_task("t1")
    assert calls.progress[0] == {"waiting": True}
    assert calls.progress[1]["total"] == 23
    result = {"total": 23, "scored": 23, "matches": 9, "below": 14, "failed": 0}
    assert calls.final == [("ready", None, result)]
    assert line == "score: 23 scored, 9 matches, 14 below threshold, 0 failed"


def test_score_task_with_nothing_waiting_is_done(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = Calls(monkeypatch)
    monkeypatch.setattr(scoring, "run_scoring", fake_run(ScoringSummary()))
    documents.score_task("t1")
    assert calls.final[0][0] == "ready"


def test_score_task_explains_why_it_did_not_run(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = Calls(monkeypatch)
    skipped = ScoringSummary(skipped_reason="monthly AI cap reached ($20.00 of $20.00)")
    monkeypatch.setattr(scoring, "run_scoring", fake_run(skipped))
    documents.score_task("t1")
    step, error, _ = calls.final[0]
    assert step == "error" and error == "Monthly AI cap reached ($20.00 of $20.00)."


def test_score_task_errors_instead_of_hanging(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = Calls(monkeypatch)
    failed = ScoringSummary(total=5, failed=5, errors=["Claude Code timed out"])
    monkeypatch.setattr(scoring, "run_scoring", fake_run(failed))
    documents.score_task("t1")
    assert calls.final[0][:2] == ("error", "Claude Code timed out")

    calls = Calls(monkeypatch)
    monkeypatch.setattr(scoring, "run_scoring", fake_run(ScoringSummary(), raises=ConnectionError("offline")))
    assert documents.score_task("t2") == "score: error: offline"
    assert calls.final[0][:2] == ("error", "offline")

    calls = Calls(monkeypatch)
    expired = AuthExpiredError("expired")
    monkeypatch.setattr(scoring, "run_scoring", fake_run(ScoringSummary(), raises=expired))
    with pytest.raises(AuthExpiredError):
        documents.score_task("t3")
    assert calls.final[0][:2] == ("error", "Claude Code sign-in expired on the Mac")


def test_score_task_taken_by_another_runner_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = Calls(monkeypatch, claimed=False)
    monkeypatch.setattr(scoring, "run_scoring", fake_run(ScoringSummary(), raises=AssertionError("ran")))
    assert documents.score_task("t1") is None
    assert calls.final == []


def test_process_tasks_scores_without_loading_the_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    Calls(monkeypatch)
    monkeypatch.setattr(db, "queued_tasks", lambda limit: [TaskRow(id="t1", job_id=None, kind="score")])

    def no_profile() -> None:
        raise AssertionError("a score task doesn't need the profile here")

    monkeypatch.setattr(db, "latest_profile", no_profile)
    monkeypatch.setattr(scoring, "run_scoring", fake_run(ScoringSummary(total=2, scored=2, kept=1, below=1)))
    assert documents.process_tasks() == ["score: 2 scored, 1 matches, 1 below threshold, 0 failed"]
