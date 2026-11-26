"""Tailored documents workflow (milestone 4).

tailor_job   write (Opus) → code checks → fact check (Sonnet) → save both documents
             and any suggestions; if nothing needs approval, render right away
render_job   apply Kojo's decisions (and edits) → fit the resume to one page →
             Word + PDF for both → upload to private Storage → job is "Docs ready"
run_tailoring   the daily best-first pass over matches without documents (capped)
process_tasks   button presses from the website: tailor, regenerate, render
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .content import CoverLetterContent, ResumeContent, Tailored
from .llm import AuthExpiredError, ClaudeCode, LLMError
from .models import JobForScoring
from .profile import Profile
from .render import RenderError, build_cover_letter, fit_one_page, to_pdf
from .tailor import tailor
from .verify import apply_decisions, code_checks, model_check, suggestions

WRITER_MODEL = "opus"
CHECKER_MODEL = "sonnet"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


# ---------------------------------------------------------------------------
# Preview: what the website shows for a document (headers filled in from the profile)
# ---------------------------------------------------------------------------


def _line(path: str, text: str, suggestion: bool) -> dict[str, Any]:
    return {"path": path, "text": text, "suggestion": suggestion}


def resume_preview(r: ResumeContent, profile: Profile) -> dict[str, Any]:
    entries = {e.id: e for e in [*profile.experience, *profile.projects]}
    sections: list[dict[str, Any]] = []
    for name, section in (("Experience", "experience"), ("Projects", "projects")):
        items = []
        for i, block in enumerate(getattr(r, section)):
            e = entries.get(block.entry_id)
            if e is None:
                continue
            dates = " – ".join(d for d in (e.start, e.end) if d)
            items.append({
                "title": e.title or e.name or block.entry_id,
                "subtitle": " · ".join(x for x in (e.org, dates) if x),
                "lines": [
                    _line(f"resume.{section}.{i}.bullets.{j}", b.text, b.suggestion)
                    for j, b in enumerate(block.bullets)
                ],
            })  # fmt: skip
        if items:
            sections.append({"heading": name, "items": items})
    return {
        "headline": r.headline,
        "summary": _line("resume.summary", r.summary.text, r.summary.suggestion) if r.summary else None,
        "sections": sections,
        "skills": [f"{s.category}: {', '.join(s.items)}" for s in r.skills],
        "suggested_skills": [
            _line(f"resume.suggested_skills.{k}", s, True) for k, s in enumerate(r.suggested_skills)
        ],
    }


def cover_preview(c: CoverLetterContent) -> dict[str, Any]:
    return {
        "greeting": c.greeting,
        "paragraphs": [
            _line(f"cover.paragraphs.{i}", p.text, p.suggestion) for i, p in enumerate(c.paragraphs)
        ],
        "closing": c.closing,
    }


# ---------------------------------------------------------------------------
# Tailor
# ---------------------------------------------------------------------------


@dataclass
class TailorResult:
    job_id: str
    suggestions: int
    rendered: bool
    cost_usd: float


def tailor_job(
    job: JobForScoring,
    profile: Profile,
    *,
    writer: ClaudeCode | None = None,
    checker: ClaudeCode | None = None,
) -> TailorResult:
    from . import db

    writer = writer or ClaudeCode(model=WRITER_MODEL, effort="medium")
    checker = checker or ClaudeCode(model=CHECKER_MODEL, effort="low")
    tailored, resp = tailor(writer, job, profile)
    tailored = code_checks(tailored, profile, job.description)
    tailored, check_resp = model_check(checker, tailored, profile)
    pending = suggestions(tailored)
    cost = resp.cost_usd + (check_resp.cost_usd if check_resp else 0.0)
    template = tailored.resume.template
    payload = {
        "resume": {
            "template": template,
            "content": {"tailored": tailored.resume.model_dump(mode="json"),
                        "preview": resume_preview(tailored.resume, profile)},
        },
        "cover_letter": {
            "template": template,
            "content": {"tailored": tailored.cover_letter.model_dump(mode="json"),
                        "preview": cover_preview(tailored.cover_letter)},
        },
        "suggestions": [s.as_row() for s in pending],
        "model": resp.model,
        "cost_usd": round(cost, 5),
    }  # fmt: skip
    db.save_tailored(job.id, payload)
    rendered = False
    if not pending:
        render_job(job.id, profile)
        rendered = True
    return TailorResult(job.id, len(pending), rendered, cost)


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")[:60]


def render_job(job_id: str, profile: Profile) -> None:
    """Render the latest resume + cover letter once no suggestion is pending."""
    from . import db

    docs = db.latest_documents(job_id)
    resume_doc, cover_doc = docs.get("resume"), docs.get("cover_letter")
    if resume_doc is None or cover_doc is None:
        raise RenderError("no tailored documents to render")
    decisions = db.suggestion_decisions([resume_doc.id, cover_doc.id])
    if any(d.decision == "pending" for d in decisions):
        raise RenderError("some suggestions are still waiting for approval")

    tailored = Tailored(
        resume=ResumeContent.model_validate(resume_doc.content["tailored"]),
        cover_letter=CoverLetterContent.model_validate(cover_doc.content["tailored"]),
    )
    approved = {d.path for d in decisions if d.decision == "approved"}
    for d in decisions:  # apply Kojo's edits to approved suggestions
        if d.decision == "approved" and d.final_text:
            _set_text(tailored, d.path, d.final_text)
    final = apply_decisions(tailored, approved)
    if len(final.cover_letter.paragraphs) < 2:
        raise RenderError("the cover letter is too short after the rejected suggestions; regenerate it")

    job = db.job_header(job_id)
    who = _slug(profile.contact.name)
    company = _slug(job.company)
    with tempfile.TemporaryDirectory(prefix="jobsearch-render-") as tmp:
        out = Path(tmp)
        rendered, resume_docx, resume_pdf = fit_one_page(
            final.resume, profile, out, f"{who}_Resume_{company}"
        )
        cover_docx = out / f"{who}_Cover_Letter_{company}.docx"
        build_cover_letter(final.cover_letter, profile, company=job.company, template=rendered.template).save(
            str(cover_docx)
        )
        cover_pdf = to_pdf(cover_docx)
        for doc, docx_path, pdf_path in (
            (resume_doc, resume_docx, resume_pdf),
            (cover_doc, cover_docx, cover_pdf),
        ):
            folder = f"{job_id}/v{doc.version}"
            docx_key = db.upload_file(f"{folder}/{docx_path.name}", docx_path.read_bytes(), DOCX_TYPE)
            pdf_key = db.upload_file(f"{folder}/{pdf_path.name}", pdf_path.read_bytes(), "application/pdf")
            db.mark_rendered(doc.id, docx_path=docx_key, pdf_path=pdf_key)
    db.mark_job_documents_ready(job_id)


def _set_text(t: Tailored, path: str, text: str) -> None:
    parts = path.split(".")
    if path == "resume.summary" and t.resume.summary is not None:
        t.resume.summary.text = text
    elif parts[:2] in (["resume", "experience"], ["resume", "projects"]) and len(parts) == 5:
        blocks = getattr(t.resume, parts[1])
        blocks[int(parts[2])].bullets[int(parts[4])].text = text
    elif parts[:2] == ["cover", "paragraphs"]:
        t.cover_letter.paragraphs[int(parts[2])].text = text
    elif parts[:2] == ["resume", "suggested_skills"]:
        t.resume.suggested_skills[int(parts[2])] = text


# ---------------------------------------------------------------------------
# Daily pass and the task queue
# ---------------------------------------------------------------------------


@dataclass
class TailoringSummary:
    tailored: int = 0
    rendered: int = 0
    waiting_for_approval: int = 0
    failed: int = 0
    cost_usd: float = 0.0
    skipped_reason: str | None = None
    errors: list[str] = field(default_factory=list)


def run_tailoring(*, limit: int, dry_run: bool = False) -> TailoringSummary:
    from . import db

    summary = TailoringSummary()
    settings = db.load_settings()
    spent = db.month_cost()
    if spent >= settings.monthly_spend_cap_usd:
        summary.skipped_reason = (
            f"monthly AI cap reached (${spent:.2f} of ${settings.monthly_spend_cap_usd:.2f})"
        )
        return summary
    row = db.latest_profile()
    if row is None:
        summary.skipped_reason = "no master profile uploaded yet"
        return summary
    profile = Profile.model_validate(row.data)
    jobs = db.jobs_to_tailor(limit=limit)
    if dry_run or not jobs:
        summary.skipped_reason = f"dry run: would tailor {len(jobs)} jobs" if dry_run else None
        return summary
    run_id = db.start_run("tailoring")
    status: Literal["succeeded", "failed"] = "succeeded"
    try:
        for job in jobs:
            try:
                res = tailor_job(job, profile)
            except AuthExpiredError as e:
                summary.errors.append(f"Claude Code sign-in expired: {e}"[:300])
                raise
            except (LLMError, RenderError) as e:
                summary.failed += 1
                summary.errors.append(f"{job.company} — {job.title}: {e}"[:300])
                db.mark_job_error(job.id)
                continue
            summary.tailored += 1
            summary.cost_usd += res.cost_usd
            summary.rendered += res.rendered
            summary.waiting_for_approval += not res.rendered
        if summary.failed and not summary.tailored:
            status = "failed"
    except Exception:
        status = "failed"
        raise
    finally:
        db.finish_run(
            run_id,
            status=status,
            counts={"tailored": summary.tailored, "rendered": summary.rendered,
                    "waiting_for_approval": summary.waiting_for_approval, "failed": summary.failed},
            error="\n".join(summary.errors) or None,
            cost_usd=summary.cost_usd,
        )  # fmt: skip
    return summary


def process_tasks(limit: int = 10) -> list[str]:
    """Handle queued button presses from the website. Returns one line per task."""
    from . import db

    done: list[str] = []
    tasks = db.queued_tasks(limit)
    if not tasks:
        return done
    row = db.latest_profile()
    if row is None:
        return ["no master profile uploaded yet"]
    profile = Profile.model_validate(row.data)
    for task in tasks:
        if task.job_id is None:
            db.update_task(task.id, "error", "task has no job")
            continue
        try:
            if task.kind in ("tailor", "regenerate"):
                db.update_task(task.id, "writing")
                job = db.jobs_by_ids([task.job_id])[0]
                res = tailor_job(job, profile)
                if res.suggestions:
                    db.update_task(task.id, "ready")
                    done.append(f"{task.kind} {job.title}: {res.suggestions} suggestions to review")
                    continue
            elif task.kind == "render":
                db.update_task(task.id, "rendering")
                render_job(task.job_id, profile)
            db.update_task(task.id, "ready")
            done.append(f"{task.kind} {task.job_id}: done")
        except AuthExpiredError:
            db.update_task(task.id, "error", "Claude Code sign-in expired on the Mac")
            raise
        except (LLMError, RenderError, IndexError) as e:
            db.update_task(task.id, "error", str(e)[:300])
            done.append(f"{task.kind} {task.job_id}: error: {e}")
    return done
