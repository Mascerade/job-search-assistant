"""Digest email: content, rendering, and mail settings (no network, no database)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from jobsearch.config import ConfigError
from jobsearch.digest import (
    Digest,
    DigestJob,
    _short_error,
    build_message,
    mail_config,
    render_html,
    render_text,
)

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)


def job(
    id: str, *, score: int | None = 70, state: str = "scored", status: str = "new", **kw: object
) -> DigestJob:
    return DigestJob.model_validate(
        {
            "id": id,
            "title": kw.get("title", f"Job {id}"),
            "company": kw.get("company", "Acme"),
            "fit_score": score,
            "fit_reason": kw.get("fit_reason", "Good fit."),
            "pipeline_state": state,
            "status": status,
            "applied_at": kw.get("applied_at"),
            "first_seen_at": NOW,
        }
    )


def test_empty_digest_is_empty() -> None:
    d = Digest(since=NOW)
    assert d.is_empty()
    assert d.subject() == "Job search · nothing new"


def test_subject_counts_and_singular() -> None:
    d = Digest(since=NOW, new_matches=[job("a")], to_review=[job("b"), job("c")], problems=["x"])
    assert d.subject() == "Job search · 1 new match, 2 to review, ⚠ needs attention"


def test_new_matches_with_documents_are_not_listed_twice() -> None:
    a, b = job("a"), job("b", state="needs_approval")
    d = Digest(since=NOW, new_matches=[a, b], to_review=[b])
    assert [j.id for j in d.new_without_documents()] == ["a"]
    out = render_html(d)
    assert "1 more new matches already have documents" in out
    assert out.count("Job b") == 1


def test_html_declares_utf8_and_escapes_text() -> None:
    d = Digest(since=NOW, new_matches=[job("a", title="R&D <Engineer>", company="Tom's")])
    out = render_html(d)
    assert '<meta charset="utf-8">' in out
    assert "R&amp;D &lt;Engineer&gt;" in out
    assert "<Engineer>" not in out


def test_links_use_site_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SITE_URL", "https://example.test/")
    d = Digest(since=NOW, ready=[job("abc", state="ready", status="docs_ready")])
    assert "https://example.test/jobs/abc" in render_html(d)
    assert "https://example.test/jobs/abc" in render_text(d)


def test_lists_are_capped_with_a_more_line() -> None:
    d = Digest(since=NOW, new_matches=[job(str(i)) for i in range(13)])
    out = render_html(d)
    assert "…and 3 more on the site." in out
    assert "Job 12" not in out


def test_follow_ups_show_days_since_applied() -> None:
    applied = datetime.now(UTC) - timedelta(days=15)
    d = Digest(since=NOW, follow_ups=[job("f", status="applied", applied_at=applied)])
    assert "applied 15 days ago" in render_html(d)
    assert "TIME TO FOLLOW UP (1)" in render_text(d)


def test_short_error_trims_httpx_noise() -> None:
    raw = (
        "workday:acme/careers: HTTPStatusError: Client error '429 Too Many Requests' for url "
        "'https://acme.wd1.myworkdayjobs.com/x'\nTraceback..."
    )
    assert _short_error(raw) == "workday:acme/careers: 429 Too Many Requests"
    assert _short_error("") == ""


def test_mail_config_requires_both_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")
    with pytest.raises(ConfigError):
        mail_config()
    monkeypatch.setenv("GMAIL_ADDRESS", "me@example.com")
    monkeypatch.delenv("DIGEST_TO", raising=False)
    cfg = mail_config()
    assert cfg.app_password == "abcdefghijklmnop"  # spaces Google shows are removed
    assert cfg.to == "me@example.com"  # defaults to sending to yourself


def test_message_has_text_and_html_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GMAIL_ADDRESS", "me@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "x")
    cfg = mail_config()
    msg = build_message(Digest(since=NOW, new_matches=[job("a")]), cfg)
    assert msg["To"] == "me@example.com"
    types = [part.get_content_type() for part in msg.iter_parts()]
    assert types == ["text/plain", "text/html"]
