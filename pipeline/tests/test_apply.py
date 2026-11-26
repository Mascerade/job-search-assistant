"""Apply assist (milestone 6): finding the job, readiness, packets, and the record after submitting."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from jobsearch import apply, db
from jobsearch.apply import (
    PacketFile,
    SubmittedRecord,
    apply_url,
    ats_of,
    blocking,
    build_packet,
    links_for,
    match_job,
    note_text,
    readiness,
    record_for_disk,
)
from jobsearch.db import ApplyJobRow, DecisionRow, DocumentRow, ProfileVersionRow
from jobsearch.profile import ApplicationAnswers, Profile, load_profile

PROFILE = load_profile(Path(__file__).parent / "fixtures" / "profile_example.yaml")
TODAY = date(2026, 11, 27)
ID = "3f9a2c1e-0000-4000-8000-000000000001"


def job(**kw: Any) -> ApplyJobRow:
    base: dict[str, Any] = {
        "id": ID,
        "company": "Formlabs",
        "title": "3D Print Optimization Engineer",
        "status": "docs_ready",
        "pipeline_state": "ready",
        "source": "greenhouse",
        "source_board": "greenhouse:formlabs",
        "source_job_id": "formlabs:7012345",
        "url": "https://careers.formlabs.com/job/7012345?gh_jid=7012345",
        "dedupe_key": "formlabs|3d print optimization engineer",
    }
    return ApplyJobRow.model_validate(base | kw)


def doc(kind: str, state: str = "final", version: int = 2) -> DocumentRow:
    return DocumentRow.model_validate(
        {"id": f"doc-{kind}", "kind": kind, "version": version, "state": state, "content": {}}
    )


DOCS = {"resume": doc("resume"), "cover_letter": doc("cover_letter")}


def levels(issues: list[apply.Issue]) -> list[tuple[str, str]]:
    return [(i.level, i.text.split(":")[0].split(" ")[0]) for i in issues]


# ---------- finding the job ----------


def test_match_job_by_id_prefix_and_words() -> None:
    rows = [job(), job(id="aaaa1111-0000-4000-8000-000000000002", company="Kayak", title="Software Engineer")]
    assert match_job(rows, ID) == [rows[0]]
    assert match_job(rows, "3f9a2c1e") == [rows[0]]
    assert match_job(rows, "formlabs print") == [rows[0]]
    assert match_job(rows, "ENGINEER") == rows  # ambiguous: both
    assert match_job(rows, "") == []
    assert match_job(rows, "abcdef12") == []  # an id prefix that matches nothing


def test_apply_url_goes_straight_to_the_form() -> None:
    assert apply_url(job()) == "https://job-boards.greenhouse.io/formlabs/jobs/7012345"
    lever = job(source="lever", source_board="lever:acme", url="https://jobs.lever.co/acme/1b2c-3d4e")
    assert apply_url(lever) == "https://jobs.lever.co/acme/1b2c-3d4e/apply"
    ashby = job(source="ashby", source_board="ashby:suno", url="https://jobs.ashbyhq.com/suno/9f8e/")
    assert apply_url(ashby) == "https://jobs.ashbyhq.com/suno/9f8e/application"
    workday = job(source="workday", url="https://mgb.wd1.myworkdayjobs.com/en-US/MGBExternal/job/123")
    assert ats_of(workday) == "workday" and apply_url(workday) == workday.url
    adzuna = job(source="adzuna", source_board="adzuna:boston", url="https://www.adzuna.com/land/ad/123")
    assert ats_of(adzuna) == "other" and apply_url(adzuna) == adzuna.url


# ---------- readiness ----------


def test_ready_job_only_asks_about_missing_answers() -> None:
    issues = readiness(job(), DOCS, [], PROFILE.application, [], TODAY)
    assert levels(issues) == [("ask", "Salary")]  # fixture has work authorization, no salary


def test_documents_must_be_final_and_approved() -> None:
    assert levels(readiness(job(), {}, [], PROFILE.application, [], TODAY))[0] == ("block", "No")
    pending = [DecisionRow(document_id="doc-resume", path="resume.summary", decision="pending")]
    issues = readiness(job(), DOCS, pending, PROFILE.application, [], TODAY)
    assert issues[0].level == "block" and "approval" in issues[0].text
    newer = {"resume": doc("resume", state="needs_approval", version=3), "cover_letter": doc("cover_letter")}
    issues = readiness(job(), newer, [], PROFILE.application, [], TODAY)
    assert issues[0].level == "block" and "approval" in issues[0].text
    rendering = {"resume": doc("resume", state="pending_render"), "cover_letter": doc("cover_letter")}
    assert readiness(job(), rendering, [], PROFILE.application, [], TODAY)[0].level == "block"


def test_closed_or_already_applied_blocks_unless_forced() -> None:
    issues = readiness(
        job(status="applied", closed_at=datetime(2026, 11, 20, tzinfo=UTC)),
        DOCS,
        [],
        PROFILE.application,
        [],
        TODAY,
    )
    assert len(blocking(issues, force=False)) == 2
    assert blocking(issues, force=True) == []
    missing_docs = readiness(job(status="applied"), {}, [], PROFILE.application, [], TODAY)
    assert blocking(missing_docs, force=True)  # --force never skips the documents


def test_site_warnings_duplicates_and_pace() -> None:
    wd = readiness(job(source="workday", url="https://x.wd1.myworkdayjobs.com/a"), DOCS, [], None, [], TODAY)
    assert any(i.level == "warn" and "sign in" in i.text for i in wd)
    assert any(i.level == "ask" and "No application answers" in i.text for i in wd)
    seen = datetime(2026, 11, 3, 15, tzinfo=UTC)
    dup = job(id="other-1", applied_at=seen, status="applied")
    assert any("same role" in i.text for i in readiness(job(), DOCS, [], PROFILE.application, [dup], TODAY))
    sibling = job(id="other-2", title="Software Engineer", dedupe_key="x", applied_at=seen, status="applied")
    assert any(
        "1 other Formlabs role" in i.text
        for i in readiness(job(), DOCS, [], PROFILE.application, [sibling], TODAY)
    )
    busy = [
        job(
            id=f"t{i}",
            company=f"Co {i}",
            dedupe_key=f"k{i}",
            applied_at=datetime(2026, 11, 27, 14, tzinfo=UTC),
        )
        for i in range(10)
    ]
    assert any(
        "10 jobs today" in i.text for i in readiness(job(), DOCS, [], PROFILE.application, busy, TODAY)
    )


# ---------- the packet ----------


def test_links_come_from_contact_with_overrides() -> None:
    p = PROFILE.model_copy(deep=True)
    p.contact.links = ["linkedin.com/in/alex", "github.com/alex", "alexexample.dev"]
    assert links_for(p) == {
        "linkedin": "https://linkedin.com/in/alex",
        "github": "https://github.com/alex",
        "website": "https://alexexample.dev",
        "portfolio": "https://alexexample.dev/work",  # from application.links
    }


def test_packet_has_what_the_form_needs() -> None:
    files = [PacketFile("resume_pdf", "/tmp/x/Alex_Resume.pdf", 2, "ab12")]
    packet = build_packet(
        job(), PROFILE, 7, date(2027, 6, 1), [], files, ["Dear team, first.", "Second."], "x" * 9000
    )
    assert packet["job"]["apply_url"] == "https://job-boards.greenhouse.io/formlabs/jobs/7012345"
    assert (packet["you"]["first_name"], packet["you"]["last_name"]) == ("Alex", "Example")
    assert packet["answers"]["earliest_start"] == "2027-06-01"
    assert packet["answers"]["how_heard"] == "Company careers site"
    assert packet["demographics"]["gender"] == "Decline to self-identify"
    assert packet["files"]["resume_pdf"]["version"] == 2
    assert packet["cover_letter_paragraphs"] == ["Dear team, first.", "Second."]
    assert len(packet["posting_text_untrusted"]) == 6000
    no_answers = PROFILE.model_copy(update={"application": None})
    adzuna = build_packet(job(source="adzuna"), no_answers, 7, date(2027, 6, 1), [], [], [], None)
    assert adzuna["answers"]["how_heard"] == "Job board (Adzuna)" and adzuna["custom_answers"] == []


# ---------- after submitting ----------

RECORD = SubmittedRecord.model_validate({
    "submitted_by": "kojo",
    "url": "https://job-boards.greenhouse.io/formlabs/jobs/7012345",
    "confirmation": "Thank you for applying.",
    "fields": [
        {"field": "First name", "value": "Alex", "source": "profile"},
        {"field": "Gender", "value": "Decline to self-identify", "source": "answer"},
        {"field": "Salary expectations", "value": "Open to discussion", "source": "kojo"},
    ],
    "essays": [
        {"question": "Why Formlabs?", "answer": "I like printers."},
        {"question": "Desired salary?", "answer": "$90k"},
    ],
})  # fmt: skip


def test_note_and_record_leave_out_sensitive_answers() -> None:
    note = note_text(job(), RECORD, {"resume": 2, "cover_letter": 2}, datetime(2026, 11, 27, 10))
    assert note.startswith(
        "Applied with apply assist on Nov 27, 2026 via Greenhouse (resume v2, cover letter v2)"
    )
    assert "Submitted by you." in note and "Why Formlabs?" in note
    assert "$90k" not in note and "Decline" not in note
    disk = record_for_disk(
        RECORD, {"files": {"resume_pdf": {"version": 2}}}, datetime(2026, 11, 27, tzinfo=UTC)
    )
    assert [f["field"] for f in disk["fields"]] == ["First name", "Salary expectations"]  # no EEO
    assert len(disk["essays"]) == 2 and disk["files"]["resume_pdf"]["version"] == 2


def test_done_marks_applied_notes_and_saves_the_record(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: dict[str, Any] = {"notes": []}
    rows = [job()]
    monkeypatch.setattr(apply, "APPLICATIONS_DIR", tmp_path)
    monkeypatch.setattr(db, "apply_candidates", lambda: rows)
    monkeypatch.setattr(db, "mark_applied", lambda job_id: rows[0].status in ("new", "docs_ready"))
    monkeypatch.setattr(db, "append_job_note", lambda job_id, text: calls["notes"].append(text))
    folder = apply.folder_for(rows[0])
    folder.mkdir(parents=True)
    (folder / "packet.json").write_text(
        json.dumps({"files": {"resume_pdf": {"version": 2}, "cover_letter_pdf": {"version": 3}}})
    )
    record = tmp_path / "record.json"
    record.write_text(RECORD.model_dump_json())

    result = apply.done("formlabs", record, now=datetime(2026, 11, 27, 15, tzinfo=UTC))
    assert not isinstance(result, list)
    assert result.moved_to_applied and "resume v2, cover letter v3" in calls["notes"][0]
    assert json.loads((folder / "submitted.json").read_text())["submitted_by"] == "kojo"

    rows[0] = job(status="interviewing")  # already further along: status stays
    again = apply.done("formlabs", record)
    assert not isinstance(again, list) and not again.moved_to_applied


def test_remember_saves_a_new_version_against_the_one_it_read(monkeypatch: pytest.MonkeyPatch) -> None:
    data = PROFILE.model_dump(mode="json", exclude_defaults=True)
    monkeypatch.setattr(
        db,
        "latest_profile",
        lambda: ProfileVersionRow(version=7, data=data, note="", created_at=datetime.now(UTC)),
    )
    saved: dict[str, Any] = {}

    def insert(d: dict[str, Any], note: str, *, base_version: int | None = None) -> int:
        saved.update(data=d, note=note, base=base_version)
        return 8

    monkeypatch.setattr(db, "insert_profile", insert)
    assert apply.remember("Do you have a driver's license?", "Yes.") == (True, 8)
    assert saved["base"] == 7 and saved["note"].startswith("Saved application answer")
    answers = Profile.model_validate(saved["data"]).application
    assert (
        isinstance(answers, ApplicationAnswers)
        and answers.answer_for("do you have a drivers license") == "Yes."
    )
    assert apply.remember("Are you open to hybrid work?", "No.") == (False, None)  # different answer exists
