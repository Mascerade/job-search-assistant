"""Adzuna aggregator: parsing, paging, key handling, and how the daily run treats it.

The fixture follows the response shape in Adzuna's docs (developer.adzuna.com/docs/search).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from jobsearch.config import ConfigError
from jobsearch.daily import AGGREGATOR_ATS, direct_companies, process_board, to_row
from jobsearch.filters import Verdict
from jobsearch.http import Http
from jobsearch.models import Board, LocationSettings, Settings, TrackSettings
from jobsearch.sources import ADZUNA_PAGE, AdzunaError, fetch

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "sources" / "adzuna_search.json").read_text())
BOARD = Board(ats="adzuna", company="Adzuna", token="Boston", search_terms=["software engineer"])
SETTINGS = Settings(
    tracks={
        "software": TrackSettings(keywords=["software engineer", "data analyst"]),
        "program_admin": TrackSettings(keywords=["program coordinator"]),
    },
    locations=LocationSettings(towns=["Boston", "Cambridge"]),
)


@pytest.fixture(autouse=True)
def keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADZUNA_APP_ID", "test-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "test-secret-key")


def http_returning(handler: Any) -> Http:
    return Http(httpx.Client(transport=httpx.MockTransport(handler)), retries=0, throttle={})


def fixture_http(seen: list[httpx.Request] | None = None) -> Http:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(200, json=FIXTURE)

    return http_returning(handler)


def test_parses_results() -> None:
    seen: list[httpx.Request] = []
    postings = fetch(BOARD, fixture_http(seen))
    assert [p.native_id for p in postings] == ["4400000001", "4400000002"]  # no-company result skipped

    first = postings[0]
    assert first.title == "Junior Software Engineer"  # search-term highlighting removed
    assert first.company == "Example Health Tech"
    assert first.locations == ["Cambridge, Middlesex County, Massachusetts"]
    assert first.employment_type == "full_time"
    assert (first.salary_min, first.salary_max) == (90000, 110000)
    assert first.url and first.url.startswith("https://www.adzuna.com/")
    assert first.posted_at is not None and first.posted_at.isoformat().startswith("2026-11-24")
    assert first.description and first.description.endswith("React…")

    second = postings[1]
    assert (second.salary_min, second.salary_max) == (None, None)  # Adzuna's guess, not the employer's
    assert second.employment_type is None  # "permanent" says nothing about hours

    params = seen[0].url.params
    assert params["title_only"] == "software engineer"
    assert params["where"] == "Boston"
    assert params["results_per_page"] == str(ADZUNA_PAGE)


def test_fetches_a_second_page_only_when_the_first_is_full() -> None:
    pages: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.path.rsplit("/", 1)[-1]
        pages.append(page)
        base = FIXTURE["results"][0]
        n = ADZUNA_PAGE if page == "1" else 3
        results = [{**base, "id": f"{page}-{i}", "title": f"Software Engineer {page}-{i}"} for i in range(n)]
        return httpx.Response(200, json={"results": results})

    postings = fetch(BOARD, http_returning(handler))
    assert pages == ["1", "2"]
    assert len(postings) == ADZUNA_PAGE + 3


def test_errors_never_include_the_keys() -> None:
    http = http_returning(lambda _req: httpx.Response(401, json={"exception": "AUTH_FAIL"}))
    with pytest.raises(AdzunaError) as info:
        fetch(BOARD, http)
    message = str(info.value)
    assert "401" in message
    assert "test-secret-key" not in message and "app_key" not in message
    assert info.value.__cause__ is None and info.value.__suppress_context__


def test_missing_keys_is_a_clear_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADZUNA_APP_KEY")
    with pytest.raises(ConfigError, match="ADZUNA_APP_KEY"):
        fetch(BOARD, fixture_http())


def test_jobs_from_employers_we_read_directly_are_skipped() -> None:
    boards = [
        Board(
            ats="peopleclick",
            company="MIT",
            token="client_mit",
            aliases=["Massachusetts Institute of Technology"],
        ),
        BOARD,
    ]
    covered = direct_companies(boards)
    assert "mit" in covered and "adzuna" not in covered

    result = process_board(BOARD, SETTINGS, fixture_http(), covered)
    assert result.error is None
    assert result.counts["covered_by_employer_site"] == 1  # MIT's copy
    assert [p.company for p, _ in result.rows] == ["Example Health Tech"]


def test_aggregator_rows_are_tagged_short_description() -> None:
    assert "adzuna" in AGGREGATOR_ATS
    p = fetch(BOARD, fixture_http())[0]
    row = to_row(p, Verdict(keep=True, track="software", tags=["location-unclear"]))
    assert row["tags"] == ["location-unclear", "short-description"]
    assert row["source"] == "adzuna"
    assert row["source_job_id"] == "Boston:4400000001"


def test_neighborhood_places_keep_their_town() -> None:
    from jobsearch.sources import _adzuna_posting

    raw = {
        **FIXTURE["results"][0],
        "location": {
            "display_name": "Harvard Square, Middlesex County",
            "area": ["US", "Massachusetts", "Middlesex County", "Cambridge", "Harvard Square"],
        },
    }
    p = _adzuna_posting(BOARD, raw)
    assert p is not None
    assert p.locations == ["Harvard Square, Cambridge, Middlesex County, Massachusetts"]


def test_the_same_job_listed_twice_is_kept_once() -> None:
    first = FIXTURE["results"][0]
    twin = {**first, "id": "4400000999"}  # same company, title, and place; different Adzuna id

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [first, twin]})

    assert [p.native_id for p in fetch(BOARD, http_returning(handler))] == ["4400000001"]
