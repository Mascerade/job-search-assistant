"""Apply assist (milestone 6): everything Claude needs to fill one application form.

    uv run jobsearch apply prepare "formlabs"       find the job, check it's ready, download its
                                                     final resume + cover letter, write packet.json
    uv run jobsearch apply done <job> --record f    after Kojo submits: mark Applied, add a note,
                                                     save submitted.json
    uv run jobsearch apply remember -q "…" -a "…"   save an approved answer to a recurring question

The /apply skill (.claude/skills/apply/SKILL.md) runs these and fills the form in Kojo's Chrome.
It stops before Submit: Kojo submits. Packets and records live in private/applications/
(gitignored); they're the lasting record of what was sent, since cleanup removes old files
from Storage.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from .config import REPO_DIR
from .profile import ApplicationAnswers, Profile

if TYPE_CHECKING:
    from .db import ApplyJobRow, DecisionRow, DocumentRow

APPLICATIONS_DIR = REPO_DIR / "private" / "applications"
DAILY_PACE_WARNING = 10
POSTING_CHARS = 6000

Ats = Literal["greenhouse", "lever", "ashby", "workday", "smartrecruiters", "other"]
FileKind = Literal["resume_pdf", "resume_docx", "cover_letter_pdf", "cover_letter_docx"]
_SOURCE_ATS: dict[str, Ats] = {
    "greenhouse": "greenhouse",
    "lever": "lever",
    "ashby": "ashby",
    "workday": "workday",
    "smartrecruiters": "smartrecruiters",
}
ATS_LABEL: dict[str, str] = {
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "workday": "Workday",
    "smartrecruiters": "SmartRecruiters",
    "other": "the employer's site",
}
_HOSTS: list[tuple[str, Ats]] = [
    ("greenhouse.io", "greenhouse"),
    ("lever.co", "lever"),
    ("ashbyhq.com", "ashby"),
    ("myworkdayjobs.com", "workday"),
    ("smartrecruiters.com", "smartrecruiters"),
]
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_PREFIX = re.compile(r"^[0-9a-f-]{6,}$")
_CLOSED_STATUSES = {"applied", "interviewing", "offer", "rejected", "withdrawn"}


# ---------------------------------------------------------------------------
# Finding the job and checking it's ready
# ---------------------------------------------------------------------------


def match_job(rows: Sequence[ApplyJobRow], query: str) -> list[ApplyJobRow]:
    """A full id, an id prefix (the website shows 8 characters), or words from the company and
    title ("formlabs 3d print"). More than one result means the query was ambiguous."""
    q = query.strip().lower()
    if not q:
        return []
    if _UUID.match(q):
        return [r for r in rows if r.id == q]
    if _PREFIX.match(q):
        by_prefix = [r for r in rows if r.id.startswith(q)]
        if by_prefix:
            return by_prefix
    words = q.split()
    return [r for r in rows if all(w in f"{r.company} {r.title}".lower() for w in words)]


def ats_of(job: ApplyJobRow) -> Ats:
    if job.source in _SOURCE_ATS:
        return _SOURCE_ATS[job.source]
    host = (job.url or "").lower()
    return next((ats for needle, ats in _HOSTS if needle in host), "other")


def apply_url(job: ApplyJobRow) -> str | None:
    """Straight to the application form: never the company page that embeds it in an iframe."""
    ats = ats_of(job)
    url = (job.url or "").rstrip("/")
    if ats == "greenhouse" and job.source == "greenhouse" and job.source_board and job.source_job_id:
        token = job.source_board.split(":", 1)[1].split("/", 1)[0]
        native = job.source_job_id.split(":", 1)[1]
        return f"https://job-boards.greenhouse.io/{token}/jobs/{native}"
    if ats == "lever" and "jobs.lever.co" in url:
        return url if url.endswith("/apply") else f"{url}/apply"
    if ats == "ashby" and "jobs.ashbyhq.com" in url:
        return url if url.endswith("/application") else f"{url}/application"
    return job.url


@dataclass(frozen=True)
class Issue:
    level: Literal["block", "warn", "ask"]
    text: str
    overridable: bool = False  # `prepare --force` may go ahead anyway


def readiness(
    job: ApplyJobRow,
    docs: dict[str, DocumentRow],
    decisions: Sequence[DecisionRow],
    answers: ApplicationAnswers | None,
    applied: Sequence[ApplyJobRow],
    today: date,
) -> list[Issue]:
    issues: list[Issue] = []
    resume, cover = docs.get("resume"), docs.get("cover_letter")
    if resume is None or cover is None:
        issues.append(
            Issue("block", "No tailored resume and cover letter yet: use Tailor now on the job page.")
        )
    elif any(d.decision == "pending" for d in decisions) or "needs_approval" in (resume.state, cover.state):
        issues.append(Issue("block", "Suggestions are waiting for your approval on the job's Documents tab."))
    elif resume.state != "final" or cover.state != "final":
        issues.append(
            Issue("block", "The documents are still being built (or failed): check the Documents tab.")
        )
    if job.closed_at is not None:
        issues.append(Issue("block", "The posting was closed by the employer.", overridable=True))
    if job.status in _CLOSED_STATUSES:
        issues.append(
            Issue("block", f"This job is already marked {job.status.replace('_', ' ')}.", overridable=True)
        )

    ats = ats_of(job)
    if ats == "workday":
        issues.append(
            Issue(
                "warn",
                f"Workday: sign in to {job.company}'s careers site first (Claude never types passwords).",
            )
        )
    elif job.source == "adzuna" and ats == "other":
        issues.append(
            Issue(
                "warn", "Adzuna link: it leads to the employer's page, where Claude will look for the form."
            )
        )
    elif ats == "other":
        issues.append(
            Issue("warn", "Unfamiliar application site: Claude will go slower and check more with you.")
        )

    others = [a for a in applied if a.id != job.id and a.applied_at is not None]
    same_role = [a for a in others if job.dedupe_key and a.dedupe_key == job.dedupe_key]
    if same_role:
        when = f"{same_role[0].applied_at:%b %-d}" if same_role[0].applied_at else "earlier"
        issues.append(Issue("warn", f"You applied to this same role from another listing ({when})."))
    same_company = [a for a in others if a.company.lower() == job.company.lower()]
    if same_company and not same_role:
        n = len(same_company)
        issues.append(Issue("warn", f"You've applied to {n} other {job.company} role{'s' if n > 1 else ''}."))
    today_count = sum(1 for a in others if a.applied_at is not None and a.applied_at.date() == today)
    if today_count >= DAILY_PACE_WARNING:
        issues.append(Issue("warn", f"You've applied to {today_count} jobs today; careful beats fast."))

    if answers is None:
        issues.append(
            Issue("ask", "No application answers saved yet: Claude will ask for each one (Profile page).")
        )
    else:
        if answers.work_authorized_us is None or answers.sponsorship_now is None:
            issues.append(Issue("ask", "Work authorization and sponsorship aren't set: Claude will ask."))
        if answers.salary_expectation is None:
            issues.append(
                Issue("ask", "Salary expectation isn't set: Claude will ask if the form requires it.")
            )
    return issues


def blocking(issues: Sequence[Issue], *, force: bool) -> list[Issue]:
    return [i for i in issues if i.level == "block" and not (force and i.overridable)]


# ---------------------------------------------------------------------------
# The packet
# ---------------------------------------------------------------------------


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def folder_for(job: ApplyJobRow) -> Path:
    """One folder per job, reused if `prepare` runs again."""
    return APPLICATIONS_DIR / f"{_slug(job.company)}-{_slug(job.title)}-{job.id[:8]}"


def links_for(profile: Profile) -> dict[str, str]:
    """LinkedIn / GitHub / website from the profile's contact links (by domain), with any
    overrides from the application answers, as full https:// URLs."""
    out: dict[str, str] = {}
    for raw in profile.contact.links:
        link = raw.strip()
        host = link.lower().removeprefix("https://").removeprefix("http://").removeprefix("www.")
        key = (
            "linkedin"
            if host.startswith("linkedin.com")
            else "github"
            if host.startswith("github.com")
            else "website"
        )
        out.setdefault(key, link)
    if profile.application:
        for key, value in profile.application.links.model_dump().items():
            if value:
                out[key] = value
    return {k: v if v.startswith(("http://", "https://")) else f"https://{v}" for k, v in out.items()}


def how_heard(job: ApplyJobRow, answers: ApplicationAnswers | None) -> str:
    if answers and answers.how_heard:
        return answers.how_heard
    return "Job board (Adzuna)" if job.source == "adzuna" else "Company careers site"


@dataclass(frozen=True)
class PacketFile:
    kind: FileKind
    path: str
    version: int
    sha256: str


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_packet(
    job: ApplyJobRow,
    profile: Profile,
    profile_version: int,
    available_from: date,
    issues: Sequence[Issue],
    files: Sequence[PacketFile],
    cover_letter_paragraphs: Sequence[str],
    posting: str | None,
) -> dict[str, Any]:
    answers = profile.application or ApplicationAnswers()
    first, _, last = profile.contact.name.partition(" ")
    return {
        "job": {
            "id": job.id,
            "short_id": job.id[:8],
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "ats": ats_of(job),
            "apply_url": apply_url(job),
            "posting_url": job.url,
        },
        "readiness": [asdict(i) for i in issues],
        "you": {
            "name": profile.contact.name,
            "first_name": first,
            "last_name": last,
            "preferred_name": answers.preferred_name,
            "email": profile.contact.email,
            "phone": profile.contact.phone,
            "location": profile.contact.location,
            "address": answers.address,
            "links": links_for(profile),
        },
        "education": [
            {"school": e.school, "degree": e.degree, "end": e.end, "location": e.location}
            for e in profile.education
        ],
        "answers": {
            "work_authorized_us": answers.work_authorized_us,
            "sponsorship_now": answers.sponsorship_now,
            "sponsorship_future": answers.sponsorship_future,
            "over_18": answers.over_18,
            "salary_expectation": answers.salary_expectation,
            "willing_to_relocate": answers.willing_to_relocate,
            "pronouns": answers.pronouns,
            "gpa": answers.gpa,
            "how_heard": how_heard(job, answers),
            "earliest_start": available_from.isoformat(),
        },
        "demographics": answers.demographics.model_dump(),
        "custom_answers": [qa.model_dump() for qa in answers.custom],
        "files": {f.kind: {"path": f.path, "version": f.version, "sha256": f.sha256} for f in files},
        "cover_letter_paragraphs": list(cover_letter_paragraphs),
        "profile_version": profile_version,
        # Employer text: data to read, never instructions to follow.
        "posting_text_untrusted": (posting or "")[:POSTING_CHARS],
    }


@dataclass
class Prepared:
    job: ApplyJobRow | None = None
    candidates: list[ApplyJobRow] | None = None  # set when the query matched several jobs
    issues: list[Issue] | None = None
    packet_path: Path | None = None


def prepare(query: str, *, force: bool = False, today: date | None = None) -> Prepared:
    from . import db
    from .documents import final_documents
    from .render import RenderError

    today = today or datetime.now().date()
    rows = db.apply_candidates()
    matches = match_job(rows, query)
    if len(matches) != 1:
        return Prepared(candidates=matches)
    job = matches[0]
    profile_row = db.latest_profile()
    if profile_row is None:
        return Prepared(job=job, issues=[Issue("block", "No master profile uploaded yet.")])
    profile = Profile.model_validate(profile_row.data)
    docs = db.latest_documents(job.id)
    decisions = db.suggestion_decisions([d.id for d in docs.values()]) if docs else []
    applied = [r for r in rows if r.applied_at is not None]
    issues = readiness(job, docs, decisions, profile.application, applied, today)
    if blocking(issues, force=force):
        return Prepared(job=job, issues=issues)

    try:
        final = final_documents(job.id)
    except RenderError as e:
        return Prepared(job=job, issues=[*issues, Issue("block", f"Documents aren't ready: {e}.")])
    folder = folder_for(job)
    folder.mkdir(parents=True, exist_ok=True)
    files: list[PacketFile] = []
    wanted: list[tuple[FileKind, DocumentRow, str | None]] = [
        ("resume_pdf", final.resume_doc, final.resume_doc.pdf_path),
        ("resume_docx", final.resume_doc, final.resume_doc.docx_path),
        ("cover_letter_pdf", final.cover_doc, final.cover_doc.pdf_path),
        ("cover_letter_docx", final.cover_doc, final.cover_doc.docx_path),
    ]
    for kind, doc, key in wanted:
        if not key:
            continue
        data = db.download_file(key)
        target = folder / Path(key).name
        target.write_bytes(data)
        files.append(PacketFile(kind, str(target), doc.version, sha256_of(data)))
    packet = build_packet(
        job,
        profile,
        profile_row.version,
        db.load_settings().available_from,
        issues,
        files,
        [p.text for p in final.final.cover_letter.paragraphs],
        db.job_description(job.id),
    )
    path = folder / "packet.json"
    path.write_text(json.dumps(packet, indent=2, ensure_ascii=False))
    return Prepared(job=job, issues=issues, packet_path=path)


# ---------------------------------------------------------------------------
# After Kojo submits
# ---------------------------------------------------------------------------

# Voluntary self-identification questions: filled from Kojo's stored choices, never recorded.
_EEO = re.compile(r"gender|race|ethnic|hispanic|latino|veteran|disab|sexual orientation|transgender")
# Pay questions: kept in the local record, but not in the job note on the website.
_PAY = re.compile(r"salary|compensation|\bpay\b")


class FieldEntry(BaseModel):
    field: str
    value: str
    source: Literal["profile", "answer", "drafted", "kojo"]


class SubmittedRecord(BaseModel):
    """What the /apply skill writes after the confirmation page shows."""

    submitted_by: Literal["kojo", "claude"]
    url: str
    confirmation: str = ""
    fields: list[FieldEntry] = Field(default_factory=list)
    essays: list[dict[str, str]] = Field(default_factory=list)  # {"question", "answer"}
    files: list[str] = Field(default_factory=list)


def is_eeo(field: str) -> bool:
    return bool(_EEO.search(field.lower()))


def is_sensitive(field: str) -> bool:
    """Demographic and pay questions stay out of the job note."""
    return is_eeo(field) or bool(_PAY.search(field.lower()))


def note_text(job: ApplyJobRow, record: SubmittedRecord, versions: dict[str, int], when: datetime) -> str:
    who = "you" if record.submitted_by == "kojo" else "Claude, after your OK"
    docs = ", ".join(f"{k.replace('_', ' ')} v{v}" for k, v in versions.items()) or "no documents"
    lines = [
        f"Applied with apply assist on {when:%b %-d, %Y} via {ATS_LABEL[ats_of(job)]} ({docs}). "
        f"Submitted by {who}."
    ]
    essays = [e for e in record.essays if e.get("question") and not is_sensitive(e["question"])]
    if essays:
        lines.append("Answers written for this application:")
        lines.extend(f"- {e['question']}\n  {e.get('answer', '').strip()}" for e in essays)
    return "\n".join(lines)


def record_for_disk(record: SubmittedRecord, packet: dict[str, Any], when: datetime) -> dict[str, Any]:
    fields = [f.model_dump() for f in record.fields if not is_eeo(f.field)]
    essays = [e for e in record.essays if not is_eeo(e.get("question", ""))]
    return {
        "submitted_at": when.isoformat(),
        "submitted_by": record.submitted_by,
        "url": record.url,
        "confirmation": record.confirmation,
        "fields": fields,
        "essays": essays,
        "files": packet.get("files", {}),
        "profile_version": packet.get("profile_version"),
    }


@dataclass
class Done:
    job: ApplyJobRow
    moved_to_applied: bool
    note: str
    record_path: Path


def done(query: str, record_path: Path, *, now: datetime | None = None) -> Done | list[ApplyJobRow]:
    from . import db

    now = now or datetime.now(UTC)
    matches = match_job(db.apply_candidates(), query)
    if len(matches) != 1:
        return matches
    job = matches[0]
    record = SubmittedRecord.model_validate_json(record_path.read_text())
    folder = folder_for(job)
    packet_file = folder / "packet.json"
    packet: dict[str, Any] = json.loads(packet_file.read_text()) if packet_file.exists() else {}
    versions = {
        kind: int(info["version"]) for kind, info in packet.get("files", {}).items() if kind.endswith("_pdf")
    }
    versions = {k.removesuffix("_pdf"): v for k, v in versions.items()}
    moved = db.mark_applied(job.id)
    note = note_text(job, record, versions, now.astimezone())
    db.append_job_note(job.id, note)
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / "submitted.json"
    out.write_text(json.dumps(record_for_disk(record, packet, now), indent=2, ensure_ascii=False))
    return Done(job=job, moved_to_applied=moved, note=note, record_path=out)


def remember(question: str, answer: str, *, replace: bool = False) -> tuple[bool, int | None]:
    """Save an approved answer to a recurring question as a new profile version.
    Returns (saved, new version); saved is False when a different answer exists and
    `replace` is off."""
    from . import db

    row = db.latest_profile()
    if row is None:
        raise ValueError("no master profile uploaded yet")
    profile = Profile.model_validate(row.data)
    if not profile.remember_answer(question, answer, replace=replace):
        return False, None
    version = db.insert_profile(
        profile.model_dump(mode="json", exclude_defaults=True),
        f"Saved application answer: {question.strip()[:80]}",
        base_version=row.version,
    )
    return True, version
