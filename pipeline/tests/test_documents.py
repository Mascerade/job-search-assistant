from pathlib import Path

from jobsearch.content import (
    CoverLetterContent,
    EntryBlock,
    Line,
    ResumeContent,
    SkillLine,
    SkillSuggestion,
    Tailored,
)
from jobsearch.documents import _set_text, cover_preview, resume_preview
from jobsearch.profile import load_profile
from jobsearch.render import _drop_least_relevant
from jobsearch.verify import apply_decisions, code_checks, suggestions

PROFILE = load_profile(Path(__file__).parent / "fixtures" / "profile_example.yaml")
# Fixture facts: acme-api "Built a REST API in Python serving 3 internal teams." (experience "acme")
#                weather-bot "Wrote a Discord bot that posts daily forecasts." (project "weather")


def tailored(
    bullets: list[Line], paragraphs: list[Line] | None = None, skills: list[str] | None = None
) -> Tailored:
    return Tailored(
        resume=ResumeContent(
            template="technical",
            experience=[EntryBlock(entry_id="acme", bullets=bullets)],
            skills=[SkillLine(category="Languages", items=skills or ["Python"])],
        ),
        cover_letter=CoverLetterContent(
            paragraphs=paragraphs
            or [Line(text="I'd love to join Example's team."), Line(text="Thank you for your time.")]
        ),
    )


def first_bullet(t: Tailored) -> Line:
    return t.resume.experience[0].bullets[0]


# ---------- code checks ----------


def test_grounded_bullet_passes() -> None:
    t = code_checks(
        tailored([Line(text="Built a Python REST API used by 3 internal teams.", fact_ids=["acme-api"])]),
        PROFILE,
        None,
    )
    assert not first_bullet(t).suggestion


def test_invented_number_becomes_a_suggestion() -> None:
    t = code_checks(
        tailored([Line(text="Built a REST API serving 12 teams.", fact_ids=["acme-api"])]), PROFILE, None
    )
    assert first_bullet(t).suggestion
    assert "12" in (first_bullet(t).rationale or "")


def test_uncited_bullet_becomes_a_suggestion() -> None:
    t = code_checks(tailored([Line(text="Led a team of engineers.")]), PROFILE, None)
    assert first_bullet(t).suggestion


def test_fact_from_another_entry_becomes_a_suggestion() -> None:
    t = code_checks(tailored([Line(text="Wrote a Discord bot.", fact_ids=["weather-bot"])]), PROFILE, None)
    assert first_bullet(t).suggestion
    assert "different role" in (first_bullet(t).rationale or "")


def test_unknown_fact_ids_are_dropped_and_unknown_entries_removed() -> None:
    t = tailored([Line(text="Built a REST API.", fact_ids=["acme-api", "made-up"])])
    t.resume.projects = [
        EntryBlock(entry_id="no-such-project", bullets=[Line(text="x", fact_ids=["acme-api"])])
    ]
    t = code_checks(t, PROFILE, None)
    assert first_bullet(t).fact_ids == ["acme-api"]
    assert t.resume.projects == []


def test_placeholder_becomes_a_suggestion() -> None:
    t = code_checks(tailored([Line(text="Cut costs by [X]%.", fact_ids=["acme-api"])]), PROFILE, None)
    assert first_bullet(t).suggestion


def test_cover_letter_may_use_numbers_from_the_posting() -> None:
    paras = [Line(text="Your team serves 167,000 customers."), Line(text="Thanks for reading.")]
    t = code_checks(
        tailored([Line(text="Built a REST API.", fact_ids=["acme-api"])], paras),
        PROFILE,
        "We serve 167,000 customers worldwide.",
    )
    assert not t.cover_letter.paragraphs[0].suggestion
    t2 = code_checks(tailored([Line(text="Built a REST API.", fact_ids=["acme-api"])], paras), PROFILE, None)
    assert t2.cover_letter.paragraphs[0].suggestion


def test_unknown_skills_move_to_suggested_skills() -> None:
    t = code_checks(
        tailored([Line(text="Built a REST API.", fact_ids=["acme-api"])], skills=["python", "Kubernetes"]),
        PROFILE,
        None,
    )
    assert t.resume.skills[0].items == ["Python"]  # canonical spelling from the profile
    assert [s.skill for s in t.resume.suggested_skills] == ["Kubernetes"]
    assert not t.resume.suggested_skills[0].obvious


# ---------- suggestions and decisions ----------


def test_suggestions_and_decisions() -> None:
    t = tailored(
        [
            Line(text="Built a REST API.", fact_ids=["acme-api"]),
            Line(text="Shipped to millions.", suggestion=True, rationale="r"),
        ],
        skills=["Python"],
    )
    t.resume.suggested_skills = [SkillSuggestion(skill="SQL", category="Languages")]
    paths = {s.path for s in suggestions(t)}
    assert paths == {"resume.experience.0.bullets.1", "resume.suggested_skills.0"}

    rejected = apply_decisions(t, approved=set())
    assert [b.text for b in rejected.resume.experience[0].bullets] == ["Built a REST API."]
    assert rejected.resume.skills[0].items == ["Python"]

    approved = apply_decisions(t, approved=paths)
    assert len(approved.resume.experience[0].bullets) == 2
    assert approved.resume.skills[0].items == ["Python", "SQL"]


def test_edits_replace_suggested_text() -> None:
    t = tailored([Line(text="Draft.", suggestion=True, rationale="r")])
    _set_text(t, "resume.experience.0.bullets.0", "Edited by Kojo.")
    _set_text(t, "cover.paragraphs.1", "New closing.")
    assert first_bullet(t).text == "Edited by Kojo."
    assert t.cover_letter.paragraphs[1].text == "New closing."


def test_previews_fill_headers_from_the_profile() -> None:
    t = tailored([Line(text="Built a REST API.", fact_ids=["acme-api"])])
    p = resume_preview(t.resume, PROFILE)
    item = p["sections"][0]["items"][0]
    assert item["title"] == "Software Intern" and "Acme Corp" in item["subtitle"]
    assert item["lines"][0]["path"] == "resume.experience.0.bullets.0"
    assert cover_preview(t.cover_letter)["paragraphs"][1]["path"] == "cover.paragraphs.1"


# ---------- one-page trimming ----------


def test_trim_drops_extra_projects_then_longest_block_bullets() -> None:
    def block(eid: str, n: int) -> EntryBlock:
        return EntryBlock(entry_id=eid, bullets=[Line(text=f"{eid} {i}") for i in range(n)])

    r = ResumeContent(
        template="technical",
        experience=[block("a", 4), block("b", 2)],
        projects=[block("p1", 2), block("p2", 1), block("p3", 1)],
    )
    assert _drop_least_relevant(r) and [b.entry_id for b in r.projects] == ["p1", "p2"]
    assert _drop_least_relevant(r) and len(r.experience[0].bullets) == 3  # the longest block loses a bullet


def test_obvious_skills_are_added_without_asking_and_uncertain_ones_capped() -> None:
    t = tailored([Line(text="Built a REST API.", fact_ids=["acme-api"])])
    t.resume.suggested_skills = [
        SkillSuggestion(skill="SQL", category="Languages", obvious=True, basis="PostgreSQL"),
        SkillSuggestion(skill="Kubernetes", category="Languages"),
        SkillSuggestion(skill="Terraform", category="Languages"),  # second uncertain: dropped
        SkillSuggestion(skill="python", category="Languages", obvious=True),  # already in the profile
    ]
    t = code_checks(t, PROFILE, None)
    assert [(s.skill, s.obvious) for s in t.resume.suggested_skills] == [("SQL", True), ("Kubernetes", False)]
    assert [s.path for s in suggestions(t)] == [
        "resume.suggested_skills.1"
    ]  # only the uncertain one is asked
    final = apply_decisions(t, approved=set())
    assert final.resume.skills[0].items == ["Python", "SQL"]


def test_declined_skills_are_never_suggested_again() -> None:
    profile = PROFILE.model_copy(deep=True)
    profile.declined_skills = ["Kubernetes"]
    t = tailored([Line(text="Built a REST API.", fact_ids=["acme-api"])], skills=["Python", "Kubernetes"])
    t = code_checks(t, profile, None)
    assert t.resume.suggested_skills == []


def test_profile_learns_and_declines_skills() -> None:
    profile = PROFILE.model_copy(deep=True)
    assert profile.add_skill("SQL", "Languages") and "sql" in profile.all_skills()
    assert not profile.add_skill("sql", "Languages")  # already there
    profile.decline_skill("Kubernetes")
    assert profile.declined_skills == ["Kubernetes"]


def test_version_one_documents_with_string_skills_still_load() -> None:
    r = ResumeContent.model_validate({"template": "admin", "suggested_skills": ["Zoom"]})
    assert r.suggested_skills[0].skill == "Zoom" and not r.suggested_skills[0].obvious
