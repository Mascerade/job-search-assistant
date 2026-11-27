from collections.abc import Sequence
from typing import Any

import pytest

from jobsearch.filters import (
    dedupe_key,
    detail_verdict,
    keyword_matches,
    location_verdict,
    normalize_employment,
    required_years,
    salary_from_text,
    title_verdict,
)
from jobsearch.models import LocationSettings, Posting, Settings, Track, TrackSettings

SETTINGS = Settings(
    experience_max_years=2,
    tracks={
        "software": TrackSettings(
            keywords=[
                "software engineer",
                "new grad",
                "machine learning engineer",
                "data analyst",
                "data scientist",
            ]
        ),
        "program_admin": TrackSettings(
            keywords=[
                "program coordinator",
                "program manager",
                "program administrator",
                "department administrator",
            ]
        ),
        "hybrid": TrackSettings(keywords=["academic technology", "research computing"]),
        "research": TrackSettings(
            keywords=["computational", "bioinformatics", "research assistant", "research associate"]
        ),
    },
    locations=LocationSettings(towns=["Boston", "Cambridge", "Somerville", "Waltham", "Newton"]),
)


def posting(
    title: str = "Software Engineer", locations: Sequence[str] = ("Boston, MA",), **kw: Any
) -> Posting:
    return Posting(
        source="greenhouse", board="greenhouse:acme", native_id="1", company="Acme", title=title,
        locations=list(locations), **kw,
    )  # fmt: skip


# ---------- titles ----------


@pytest.mark.parametrize(
    ("keyword", "title"),
    [
        ("program coordinator", "Coordinator, Graduate Programs"),
        ("software engineer", "Engineer, Software (Platform)"),
        ("software engineer", "Software Engineer I"),
        ("data analyst", "Analyst, Data & Reporting"),
    ],
)
def test_keyword_matching_is_order_free(keyword: str, title: str) -> None:
    assert keyword_matches(keyword, title)


@pytest.mark.parametrize(
    ("title", "track"),
    [
        ("Software Engineer, New Grad 2027", "software"),
        ("Program Manager, Student Affairs", "program_admin"),  # "manager" is fine for admin
        ("Program Coordinator II", "program_admin"),
        ("Academic Technology Specialist", "hybrid"),
        ("Machine Learning Engineer", "software"),
        ("Computational Associate I", "research"),
        ("Early Career Researchers - Computational Associate I, Broad-wide openings", "research"),
        ("Associate Computational Biologist", "research"),
        ("Bioinformatics Analyst", "research"),
        ("Research Assistant I", "research"),
        ("Software Engineer, Computational Policy Lab", "software"),  # the longer keyword wins
    ],
)
def test_entry_level_titles_are_kept(title: str, track: Track) -> None:
    v = title_verdict(title, SETTINGS)
    assert v.keep, v.reason
    assert v.track == track


@pytest.mark.parametrize(
    "title",
    [
        "Senior Software Engineer",
        "Sr. Data Analyst",
        "Staff Software Engineer",  # "staff" means senior in engineering…
        "Software Engineering Manager",
        "Software Engineer III",
        "Lead Program Coordinator",
        "Software Engineer Intern",
        "Program Coordinator (Part-Time)",
        "Postdoctoral Fellow, Research Computing",
        "New Graduate Registered Nurse",  # matches "new grad" but is clinical
        "Postdoctoral Associate, Computational Biology",
        "Clinical Research Associate Manager",
        "Staff Computational Scientist",
    ],
)
def test_senior_or_non_full_time_titles_are_filtered(title: str) -> None:
    assert not title_verdict(title, SETTINGS).keep


def test_staff_assistant_style_admin_titles_survive() -> None:
    # …but "staff" isn't excluded for program-admin titles.
    assert title_verdict("Staff Program Coordinator", SETTINGS).keep


def test_unrelated_title_has_no_track() -> None:
    v = title_verdict("Executive Chef", SETTINGS)
    assert not v.keep and v.track is None


def test_disabled_track_is_ignored() -> None:
    s = SETTINGS.model_copy(deep=True)
    s.tracks["hybrid"].enabled = False
    assert title_verdict("Academic Technology Specialist", s).track is None


# ---------- locations ----------


@pytest.mark.parametrize(
    "loc",
    [
        "Waltham, MA",
        "Boston, Massachusetts, United States",
        "Allston, MA",
        "Longwood Medical Area, Boston",
        "Cambridge",
    ],
)
def test_greater_boston_is_kept(loc: str) -> None:
    assert location_verdict(posting(locations=[loc]), SETTINGS).keep


@pytest.mark.parametrize(
    ("loc", "reason_part"),
    [
        ("Springfield, MA", "outside your towns"),
        ("New York, NY", "outside the Boston area"),
        ("Cambridge, United Kingdom", "outside the Boston area"),
        ("Remote - Canada", "outside the US"),
    ],
)
def test_out_of_area_is_filtered(loc: str, reason_part: str) -> None:
    v = location_verdict(posting(locations=[loc]), SETTINGS)
    assert not v.keep
    assert v.reason is not None and reason_part in v.reason


def test_us_remote_is_kept_and_marked_remote() -> None:
    v = location_verdict(posting(locations=["Remote - US"]), SETTINGS)
    assert v.keep and v.remote_type == "remote"


def test_multi_location_with_one_local_is_kept() -> None:
    assert location_verdict(posting(locations=["New York, NY", "Boston, MA"]), SETTINGS).keep


def test_hybrid_respects_setting() -> None:
    p = posting(locations=["Boston, MA"], remote_type="hybrid")
    assert location_verdict(p, SETTINGS).remote_type == "hybrid"
    s = SETTINGS.model_copy(deep=True)
    s.locations.include_hybrid = False
    assert not location_verdict(p, s).keep


def test_unclear_location_is_kept_with_tag() -> None:
    for locs in ([], ["Massachusetts"], ["2 Locations"]):
        v = location_verdict(posting(locations=locs), SETTINGS)
        assert v.keep and "location-unclear" in v.tags


# ---------- details ----------


@pytest.mark.parametrize(
    ("text", "years"),
    [
        ("Requirements: 5+ years of professional software experience.", 5),
        ("Minimum of three years of experience in higher education administration.", 3),
        ("3-5 years of relevant experience required.", 3),
        ("Bachelor's degree. 1 year of experience with Python.", 1),
        ("2+ years of experience preferred.", None),  # preferred, not required
        ("We've been building products for 10 years.", None),  # not about experience
        ("A four-year degree and some experience with Excel.", None),
        ("Minimum of four years' post-secondary education or relevant work experience.", None),
        ("0-3 years of related office experience.", 0),
        ("Minimum 2 years of professional experience, preferably in policy evaluation.", 2),
    ],
)
def test_required_years(text: str, years: int | None) -> None:
    assert required_years(text) == years


def test_obvious_experience_mismatch_is_filtered_but_borderline_kept() -> None:
    assert not detail_verdict(posting(description="5+ years of experience required."), SETTINGS).keep
    assert detail_verdict(
        posting(description="4+ years of experience required."), SETTINGS
    ).keep  # AI decides
    assert detail_verdict(posting(description="3+ years of experience required."), SETTINGS).keep


LAB_JOB = "Prepare samples, run PCR and flow cytometry, and maintain the mouse colony."
CODING_JOB = "Analyze single-cell sequencing data in Python or R and maintain analysis pipelines."


@pytest.mark.parametrize(
    ("title", "description", "keep"),
    [
        ("Research Assistant I", CODING_JOB, True),
        ("Research Assistant I", LAB_JOB, False),
        ("Research Associate II", "Experience with R packages and Bioconductor.", True),
        ("Research Associate II", "Support R&D lab operations.", False),  # "R&D" isn't R
        ("Research Assistant, Data Analysis", LAB_JOB, True),  # the title already says data
        ("Computational Associate I", LAB_JOB, True),
        (
            "Research Associate II",
            "Run screens. Collaborate with experimentalists and computational biologists.",
            False,
        ),
        (
            "Research Associate II",
            "Use Fiji, CellProfiler, Python, or R (programming experience is not required).",
            False,
        ),
        (
            "Research Assistant I",
            "Strong computational skills and experience with statistical analysis.",
            True,
        ),
    ],
)
def test_research_titles_need_programming_unless_the_title_says_so(
    title: str, description: str, keep: bool
) -> None:
    v = detail_verdict(posting(title, description=description), SETTINGS, "research")
    assert v.keep is keep
    if not keep:
        assert v.reason == "research role without programming"


def test_programming_check_only_applies_to_research() -> None:
    assert detail_verdict(posting("Research Assistant I", description=LAB_JOB), SETTINGS, "hybrid").keep
    assert detail_verdict(posting("Research Assistant I", description=None), SETTINGS, "research").keep


def test_clearance_and_part_time_are_filtered() -> None:
    assert not detail_verdict(posting(description="Must hold an active TS/SCI clearance."), SETTINGS).keep
    assert not detail_verdict(posting(employment_type="part_time"), SETTINGS).keep
    assert detail_verdict(posting(employment_type="full_time"), SETTINGS).keep


# ---------- helpers ----------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The salary range is $65,000 - $80,000 per year.", (65000, 80000)),
        ("Pay: $90k–$120k", (90000, 120000)),
        ("$100,000.00 to $130,000.00", (100000, 130000)),
        ("Hourly: $25.00 - $30.00", (None, None)),
        ("No pay info", (None, None)),
    ],
)
def test_salary_from_text(text: str, expected: tuple[int | None, int | None]) -> None:
    assert salary_from_text(text) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Full time", "full_time"), ("FullTime", "full_time"), ("Part-Time", "part_time"), ("Intern", "intern"),
     ("Contract", "contract"), ("Temporary", "temporary"), (None, None)],
)  # fmt: skip
def test_normalize_employment(raw: str | None, expected: str | None) -> None:
    assert normalize_employment(raw) == expected


def test_dedupe_key_ignores_location_suffix_in_title() -> None:
    a = posting(title="Software Engineer - Boston", locations=["Boston, MA"])
    b = posting(title="Software Engineer (Hybrid)", locations=["Boston, MA, United States"])
    assert dedupe_key(a) == dedupe_key(b) == "acme|software engineer|boston"


def test_workday_boards_run_locally_everything_else_in_the_cloud() -> None:
    from jobsearch.daily import load_boards, runs_where

    boards = load_boards()
    assert {runs_where(b) for b in boards if b.ats == "workday"} == {"local"}
    assert {runs_where(b) for b in boards if b.ats != "workday"} == {"cloud"}
