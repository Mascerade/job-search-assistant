"""The morning digest email (milestone 5).

Sent from the Mac at the end of `jobsearch local-daily`, from Kojo's Gmail to Kojo's
Gmail (an app password in pipeline/.env.production). It covers everything since the
last digest that was sent:

  - new matches (fit score, reason, link)
  - documents waiting for review, and documents ready to download
  - applications sitting in "Applied" for 14+ days (time to follow up or close them)
  - problems: failed runs, boards that couldn't be fetched, an expiring Claude sign-in,
    the AI usage cap

Nothing to report → nothing is sent.

    uv run jobsearch digest --dry-run      # print it and save a preview HTML; send nothing
    uv run jobsearch digest                # send
"""

from __future__ import annotations

import html
import os
import re
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any

from pydantic import BaseModel

from .config import ConfigError
from .models import STAFFING_AGENCY_TAG

MATCH_STATES = ("scored", "needs_approval", "tailoring", "ready")
FOLLOW_UP_DAYS = 14
LIST_LIMIT = 10
DEFAULT_SITE = "https://job-search-assistant-seven.vercel.app"


class DigestJob(BaseModel):
    id: str
    title: str
    company: str
    location: str | None = None
    fit_score: int | None = None
    fit_reason: str | None = None
    pipeline_state: str
    status: str
    applied_at: datetime | None = None
    first_seen_at: datetime
    tags: list[str] = []

    def employer(self) -> str:
        """Company name, marked when it's a staffing agency posting for someone else."""
        return self.company + (" (staffing agency)" if STAFFING_AGENCY_TAG in self.tags else "")


@dataclass
class Digest:
    since: datetime
    new_matches: list[DigestJob] = field(default_factory=list)
    to_review: list[DigestJob] = field(default_factory=list)
    ready: list[DigestJob] = field(default_factory=list)
    follow_ups: list[DigestJob] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def new_without_documents(self) -> list[DigestJob]:
        """New matches not already listed under review/ready (avoids listing a job twice)."""
        listed = {j.id for j in [*self.to_review, *self.ready]}
        return [j for j in self.new_matches if j.id not in listed]

    def is_empty(self) -> bool:
        return not (self.new_matches or self.to_review or self.ready or self.follow_ups or self.problems)

    def subject(self) -> str:
        bits = []
        if self.new_matches:
            bits.append(f"{len(self.new_matches)} new {'match' if len(self.new_matches) == 1 else 'matches'}")
        if self.to_review:
            bits.append(f"{len(self.to_review)} to review")
        if self.ready:
            bits.append(f"{len(self.ready)} ready to apply")
        if self.follow_ups:
            bits.append(f"{len(self.follow_ups)} to follow up")
        if self.problems:
            bits.append("⚠ needs attention")
        return "Job search · " + (", ".join(bits) or "nothing new")


# ---------------------------------------------------------------------------
# Gathering
# ---------------------------------------------------------------------------

_COLUMNS = (
    "id, title, company, location, fit_score, fit_reason, pipeline_state, status, applied_at, first_seen_at, tags"
)


def gather(now: datetime | None = None) -> Digest:
    from . import db
    from .db import _rows

    now = now or datetime.now(UTC)
    since = db.last_run_start("digest") or now - timedelta(days=1)
    d = Digest(since=since)
    # Ask only for the rows each section needs (the API returns at most 1,000 rows a request).
    open_matches = _rows(
        db.client()
        .table("jobs")
        .select(_COLUMNS)
        .is_("closed_at", "null")
        .in_("pipeline_state", list(MATCH_STATES))
        .execute()
        .data,
        DigestJob,
    )
    cutoff = now - timedelta(days=FOLLOW_UP_DAYS)
    # Applied jobs whatever their posting's state: postings often close after you apply.
    d.follow_ups = _rows(
        db.client()
        .table("jobs")
        .select(_COLUMNS)
        .eq("status", "applied")
        .lte("applied_at", cutoff.isoformat())
        .order("applied_at")
        .execute()
        .data,
        DigestJob,
    )
    by_fit = sorted(open_matches, key=lambda j: -(j.fit_score or 0))
    d.new_matches = [j for j in by_fit if j.pipeline_state in MATCH_STATES and j.first_seen_at >= since]
    d.to_review = [
        j for j in by_fit if j.pipeline_state == "needs_approval" and j.status in ("new", "docs_ready")
    ]
    d.ready = [j for j in by_fit if j.pipeline_state == "ready" and j.status == "docs_ready"]
    d.problems = problems(since, now)
    return d


_HTTP_ERROR = re.compile(r"HTTPStatusError: (?:Client|Server) error '(\d{3} [^']*)' for url '[^']*'")


def _short_error(text: str) -> str:
    """First line of an error, with httpx's long 'Client error ... for url ...' cut to '429 Too Many Requests'."""
    first = text.strip().splitlines()[0] if text.strip() else ""
    return _HTTP_ERROR.sub(r"\1", first)[:200]


def problems(since: datetime, now: datetime) -> list[str]:
    from . import db

    out: list[str] = []
    for run in db.runs_since(since):
        first_line = _short_error(run.error or "")
        if run.status == "failed":
            out.append(
                f"The {run.kind} run on {run.started_at:%b %d} failed"
                + (f": {first_line}" if first_line else ".")
            )
        elif run.error and run.kind in ("daily", "local"):
            failed = run.counts.get("boards_failed", 0)
            out.append(f"{failed or 'Some'} job board(s) couldn't be fetched ({run.kind} run): {first_line}")
        elif run.status == "running" and run.started_at < now - timedelta(hours=3):
            out.append(f"A {run.kind} run started {run.started_at:%b %d %H:%M} UTC never finished.")
    days = db.latest_signin_days_left()
    if days is not None and days <= 10:
        out.append(f"Your Claude Code sign-in ends in {days} days; run `claude` → /login on your Mac.")
    settings = db.load_settings()
    spent = db.month_cost(now)
    if settings.monthly_spend_cap_usd and spent >= 0.8 * settings.monthly_spend_cap_usd:
        out.append(
            f"AI usage this month is ${spent:.2f} of your ${settings.monthly_spend_cap_usd:.0f} cap "
            "(estimated; free on your Claude plan). AI steps pause at the cap; raise it in Settings."
        )
    return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

PRIMARY, TEXT, MUTED, BORDER = "#0369A1", "#0C4A6E", "#475569", "#BAE6FD"


def _site() -> str:
    return os.environ.get("SITE_URL", DEFAULT_SITE).rstrip("/")


def _job_link(j: DigestJob) -> str:
    return f"{_site()}/jobs/{j.id}"


def _section_html(title: str, jobs: list[DigestJob], *, note: str = "", detail: Any = None) -> str:
    if not jobs:
        return ""
    rows = []
    for j in jobs[:LIST_LIMIT]:
        score = (
            f'<span style="font-family:monospace;color:{PRIMARY}">{j.fit_score}</span> · '
            if j.fit_score
            else ""
        )
        extra = detail(j) if detail else (j.fit_reason or "")
        rows.append(
            f'<li style="margin:0 0 10px 0"><a href="{html.escape(_job_link(j))}" '
            f'style="color:{PRIMARY};font-weight:600;text-decoration:none">{html.escape(j.title)}</a>'
            f' <span style="color:{MUTED}">— {html.escape(j.employer())}</span><br>'
            f'<span style="color:{MUTED};font-size:13px">{score}{html.escape(extra)}</span></li>'
        )
    more = (
        f'<p style="color:{MUTED};font-size:13px">…and {len(jobs) - LIST_LIMIT} more on the site.</p>'
        if len(jobs) > LIST_LIMIT
        else ""
    )
    note_html = (
        f'<p style="color:{MUTED};font-size:13px;margin:0 0 8px">{html.escape(note)}</p>' if note else ""
    )
    return (
        f'<h2 style="font-size:15px;color:{TEXT};margin:22px 0 8px;padding-bottom:4px;border-bottom:1px solid {BORDER}">'
        f"{html.escape(title)} ({len(jobs)})</h2>{note_html}"
        f'<ul style="padding-left:18px;margin:0">{"".join(rows)}</ul>{more}'
    )


def _days_ago(j: DigestJob) -> str:
    if j.applied_at is None:
        return ""
    return f"applied {(datetime.now(UTC) - j.applied_at).days} days ago"


def render_html(d: Digest) -> str:
    parts = [
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"></head><body>',
        f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.5;color:{TEXT};max-width:640px">',
        f'<h1 style="font-size:18px;margin:0 0 4px">Your job search this morning</h1>'
        f'<p style="color:{MUTED};margin:0 0 8px">Since {d.since:%b %d, %H:%M} UTC · '
        f'<a href="{_site()}" style="color:{PRIMARY}">Open the site</a></p>',
    ]
    if d.problems:
        items = "".join(f'<li style="margin-bottom:6px">{html.escape(p)}</li>' for p in d.problems)
        parts.append(
            '<div style="border:1px solid #B45309;border-radius:8px;padding:10px 14px;margin:14px 0;background:#FEF3C7">'
            f'<strong style="color:#B45309">Needs attention</strong><ul style="margin:6px 0 0;padding-left:18px">{items}</ul></div>'
        )
    new_only = d.new_without_documents()
    overlap = len(d.new_matches) - len(new_only)
    note = f"{overlap} more new matches already have documents (below)." if overlap else ""
    parts.append(_section_html("New matches", new_only, note=note))
    parts.append(
        _section_html("Review suggestions", d.to_review, note="Approve, edit, or reject to get the PDFs.")
    )
    parts.append(
        _section_html("Ready to apply", d.ready, note="Resume and cover letter are ready to download.")
    )
    parts.append(
        _section_html(
            "Time to follow up", d.follow_ups, note="Still in Applied after two weeks.", detail=_days_ago
        )
    )
    parts.append(
        f'<p style="color:{MUTED};font-size:12px;margin-top:24px">Sent by your job search assistant from your Mac. '
        "Nothing new on a given day means no email.</p></div></body></html>"
    )
    return "".join(p for p in parts if p)


def render_text(d: Digest) -> str:
    lines = [f"Your job search this morning (since {d.since:%b %d %H:%M} UTC)", _site(), ""]
    if d.problems:
        lines += ["NEEDS ATTENTION", *[f"- {p}" for p in d.problems], ""]
    for title, jobs in (
        ("NEW MATCHES (documents not written yet)", d.new_without_documents()),
        ("REVIEW SUGGESTIONS", d.to_review),
        ("READY TO APPLY", d.ready),
        ("TIME TO FOLLOW UP", d.follow_ups),
    ):
        if jobs:
            lines.append(f"{title} ({len(jobs)})")
            for j in jobs[:LIST_LIMIT]:
                score = f"[{j.fit_score}] " if j.fit_score else ""
                lines.append(f"- {score}{j.title} — {j.employer()}: {_job_link(j)}")
            lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MailConfig:
    address: str
    app_password: str
    to: str


def mail_config() -> MailConfig:
    address = os.environ.get("GMAIL_ADDRESS", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not address or not password:
        raise ConfigError(
            "Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in pipeline/.env.production to send the digest."
        )
    return MailConfig(address, password, os.environ.get("DIGEST_TO", "").strip() or address)


def build_message(d: Digest, cfg: MailConfig) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = d.subject()
    msg["From"] = f"Job Search Assistant <{cfg.address}>"
    msg["To"] = cfg.to
    msg.set_content(render_text(d))
    msg.add_alternative(render_html(d), subtype="html")
    return msg


def send(msg: EmailMessage, cfg: MailConfig) -> None:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30) as smtp:
        smtp.login(cfg.address, cfg.app_password)
        smtp.send_message(msg)


def run_digest(*, dry_run: bool = False) -> tuple[Digest, str]:
    """Gather and (unless dry_run or empty) send. Returns the digest and what happened."""
    from . import db

    d = gather()
    if dry_run:
        return d, "dry run: not sent"
    if d.is_empty():
        return d, "nothing new: not sent"
    cfg = mail_config()
    run_id = db.start_run("digest")
    try:
        send(build_message(d, cfg), cfg)
    except Exception as e:
        db.finish_run(run_id, status="failed", counts={}, error=f"{type(e).__name__}: {e}"[:500])
        raise
    db.finish_run(
        run_id,
        status="succeeded",
        counts={"new_matches": len(d.new_matches), "to_review": len(d.to_review), "ready": len(d.ready),
                "follow_ups": len(d.follow_ups), "problems": len(d.problems)},
    )  # fmt: skip
    return d, f"sent to {cfg.to}"
