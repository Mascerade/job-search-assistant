"""Staffing-agency postings: detection, tagging, tailoring order, digest label."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jobsearch.daily import load_staffing_agencies
from jobsearch.digest import DigestJob
from jobsearch.filters import is_staffing_agency
from jobsearch.models import STAFFING_AGENCY_TAG, JobForScoring, Settings
from jobsearch.priority import tailoring_order

KNOWN = load_staffing_agencies()  # the real config/staffing_agencies.yaml


def agency(company: str, description: str | None = None, *, aggregator: bool = True) -> bool:
    return is_staffing_agency(company, description, KNOWN, read_description=aggregator)


def test_config_loads_normalized_names() -> None:
    assert {"adecco", "kelly services", "teksystems", "cynet systems"} <= KNOWN


@pytest.mark.parametrize(
    "company",
    [
        "Adecco US, Inc.",  # listed name + suffix
        "CYNET SYSTEMS",  # capitals
        "Kelly Services",
        "Motion Recruitment Partners, LLC",
        "The Judge Group",  # "The" ignored
        "Lighthouse Staffing",  # not listed, caught by the word
        "Boston Recruiting Partners",
    ],
)
def test_agencies_are_recognized(company: str) -> None:
    assert agency(company)


@pytest.mark.parametrize(
    "company",
    [
        "Wellington Management",
        "Cambridge Health Alliance",
        "Beacon Hill Village",  # a nonprofit, not Beacon Hill Staffing
        "Voltage Park",  # "Volt" only matches whole words
        "Atrium Health",
        "Harvard University",
    ],
)
def test_employers_are_not_agencies(company: str) -> None:
    assert not agency(company)


def test_our_client_wording_counts_only_for_aggregator_postings() -> None:
    text = "Our client, a leading Boston biotech, is hiring a program coordinator..."
    assert agency("Acme Talent Partners", text)
    assert not agency("Acme Talent Partners", text, aggregator=False)
    assert agency("Acme Talent Partners", "Remote. Our client seeks a curious People Data Analyst")
    assert agency("Acme Talent Partners", "Hiring on behalf of our client in Cambridge")
    assert not agency("Acme Consulting", "We help our clients modernize their data platforms.")
    assert not agency("Acme Consulting", "turnkey solutions tailored to our client's needs")
    assert not agency("Acme Consulting", "to support our client’s AML integration")


def job(id: str, *tags: str) -> JobForScoring:
    return JobForScoring(id=id, company="X", title="T", track="software", tags=list(tags))


def test_agency_jobs_are_tailored_after_direct_employers() -> None:
    jobs = [  # as the database returns them: best fit first
        job("agency-90", STAFFING_AGENCY_TAG),
        job("direct-80"),
        job("agency-75", STAFFING_AGENCY_TAG, "short-description"),
        job("direct-60", "location-unclear"),
    ]
    order = tailoring_order(jobs, Settings(focus_until=None))
    assert [j.id for j in order] == ["direct-80", "direct-60", "agency-90", "agency-75"]


def test_digest_marks_agency_postings() -> None:
    base = {
        "id": "1",
        "title": "Project Coordinator",
        "pipeline_state": "scored",
        "status": "new",
        "first_seen_at": datetime(2026, 11, 26, tzinfo=UTC),
    }
    assert DigestJob.model_validate(
        base | {"company": "Actalent", "tags": [STAFFING_AGENCY_TAG]}
    ).employer() == ("Actalent (staffing agency)")
    assert DigestJob.model_validate(base | {"company": "MIT"}).employer() == "MIT"
