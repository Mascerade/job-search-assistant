"""Tailoring order: timing focus until a date, future starts first, agencies last."""

from __future__ import annotations

from datetime import date

from jobsearch.models import FUTURE_START_TAG, STAFFING_AGENCY_TAG, JobForScoring, Settings, Track
from jobsearch.priority import in_focus_window, tailoring_order

FOCUS = Settings(focus_until=date(2027, 3, 1))
BEFORE, AFTER = date(2026, 11, 27), date(2027, 3, 1)


def job(id: str, track: Track, *tags: str) -> JobForScoring:
    return JobForScoring(id=id, company="X", title="T", track=track, tags=list(tags))


JOBS = [  # best fit first, as the database returns them
    job("admin-90", "program_admin"),
    job("hybrid-85", "hybrid"),
    job("agency-sw-84", "software", STAFFING_AGENCY_TAG),
    job("software-80", "software"),
    job("admin-newgrad-70", "program_admin", FUTURE_START_TAG),
    job("software-60", "software"),
]


def ids(jobs: list[JobForScoring]) -> list[str]:
    return [j.id for j in jobs]


def test_focus_window_puts_software_then_hybrid_then_admin() -> None:
    assert ids(tailoring_order(JOBS, FOCUS, BEFORE)) == [
        "admin-newgrad-70",  # tied to a future start: right timing, any track
        "software-80",
        "software-60",
        "hybrid-85",
        "admin-90",
        "agency-sw-84",  # agencies always last
    ]


def test_after_the_date_it_is_best_fit_with_agencies_last() -> None:
    assert ids(tailoring_order(JOBS, FOCUS, AFTER)) == [
        "admin-90",
        "hybrid-85",
        "software-80",
        "admin-newgrad-70",
        "software-60",
        "agency-sw-84",
    ]


def test_no_date_means_no_focus() -> None:
    assert not in_focus_window(Settings(focus_until=None), BEFORE)
    assert in_focus_window(FOCUS, BEFORE) and not in_focus_window(FOCUS, AFTER)


def test_settings_default_focus_date_and_json_round_trip() -> None:
    assert Settings().focus_until == date(2027, 3, 1)
    assert Settings.model_validate({"focus_until": "2027-04-15"}).focus_until == date(2027, 4, 15)
    assert Settings.model_validate({"focus_until": None}).focus_until is None
