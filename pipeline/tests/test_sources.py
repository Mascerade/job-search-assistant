"""Adapters parsed against real (trimmed) responses saved in tests/fixtures/sources/."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from jobsearch.http import Http
from jobsearch.models import Ats, Board, Posting
from jobsearch.sources import enrich, fetch

FIX = Path(__file__).parent / "fixtures" / "sources"


def routes(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    table = {
        "boards-api.greenhouse.io": "greenhouse_jobs.json",
        "api.lever.co": "lever_postings.json",
        "api.ashbyhq.com": "ashby_job_board.json",
        "jobs.tufts.edu/api/jobs": "jibe_jobs.json",
        "jobs.silkroad.com": "silkroad.xml",
        "pageuppeople.com": "pageup.xml",
        "/getJobs": "peopleclick_jobs.json",
    }
    if "myworkdayjobs.com" in url:
        name = "workday_jobs.json" if request.method == "POST" else "workday_job_detail.json"
        return httpx.Response(200, content=(FIX / name).read_bytes())
    if "api.smartrecruiters.com" in url:
        name = (
            "smartrecruiters_list.json"
            if url.split("?")[0].endswith("/postings")
            else "smartrecruiters_detail.json"
        )
        return httpx.Response(200, content=(FIX / name).read_bytes())
    if "avature.net" in url:
        if "/SearchJobs" in url:
            offset = request.url.params.get("jobOffset", "0")
            name = "avature_list_2.html" if offset == "3" else "avature_list_1.html"  # then repeats
        else:
            name = "avature_detail.html"
        return httpx.Response(200, content=(FIX / name).read_bytes())
    if "careers.peopleclick.com" in url and "/getJobs" not in url:
        return httpx.Response(200, text="<html>search page</html>")  # cookie handshake
    for needle, name in table.items():
        if needle in url:
            return httpx.Response(200, content=(FIX / name).read_bytes())
    return httpx.Response(404)


@pytest.fixture
def http() -> Http:
    return Http(httpx.Client(transport=httpx.MockTransport(routes)), retries=0)


def board(ats: Ats, token: str, **kw: Any) -> Board:
    return Board(ats=ats, company="Example", token=token, **kw)


def assert_clean(postings: list[Posting]) -> None:
    assert postings, "no postings parsed"
    for p in postings:
        assert p.title and p.native_id
        assert p.url and p.url.startswith("https://")
        assert p.source_job_id.startswith(p.board.split(":", 1)[1] + ":")
        if p.description:
            assert "<p>" not in p.description and "&lt;" not in p.description


def test_greenhouse(http: Http) -> None:
    ps = fetch(board("greenhouse", "cargurus"), http)
    assert_clean(ps)
    assert ps[0].locations == ["Boston, Massachusetts, United States"]
    assert ps[0].description and len(ps[0].description) > 200  # entity-escaped HTML was decoded
    assert ps[0].posted_at is not None


def test_lever(http: Http) -> None:
    ps = fetch(board("lever", "cfsenergy"), http)
    assert_clean(ps)
    first = ps[0]
    assert first.locations[0].startswith("Devens")
    assert first.remote_type == "hybrid"
    assert first.description


def test_ashby_uses_workplace_type_not_is_remote(http: Http) -> None:
    ps = fetch(board("ashby", "snyk"), http)
    assert_clean(ps)
    assert ps[0].remote_type == "hybrid"  # Ashby sets isRemote=true on hybrid jobs
    assert ps[0].employment_type == "full_time"


def test_workday_list_then_detail(http: Http) -> None:
    b = board("workday", "northeastern", wd=1, site="careers")
    ps = fetch(b, http)
    assert_clean(ps)
    assert all(p.needs_detail for p in ps)
    p = enrich(ps[0], b, http)
    assert not p.needs_detail
    assert p.description and len(p.description) > 500
    assert p.employment_type == "full_time"
    assert p.posted_at is not None and p.posted_at.date() == date(
        2026, 11, 25
    )  # from startDate, not "Posted Yesterday"


def test_smartrecruiters_list_then_detail(http: Http) -> None:
    b = board("smartrecruiters", "HarvardUniversity")
    ps = fetch(b, http)
    assert_clean(ps)
    assert ps[0].employment_type == "full_time"
    p = enrich(ps[0], b, http)
    assert p.description and p.url and "jobs.smartrecruiters.com" in p.url


def test_jibe(http: Http) -> None:
    ps = fetch(board("jibe", "jobs.tufts.edu"), http)
    assert_clean(ps)
    assert ps[0].remote_type == "hybrid"  # from tags1 ["Hybrid"]
    assert ps[0].employment_type == "full_time"


def test_silkroad_rss_tames_all_caps_titles(http: Http) -> None:
    ps = fetch(board("silkroad", "BU", feed_url="https://jobs.silkroad.com/BU/External/rss"), http)
    assert_clean(ps)
    assert not ps[0].title.split(",")[0].isupper()
    assert ps[0].employment_type == "full_time"


def test_pageup_rss(http: Http) -> None:
    ps = fetch(
        board("pageup", "umb", feed_url="https://careers.pageuppeople.com/822/boston/en-us/rss/"), http
    )
    assert_clean(ps)
    assert ps[0].locations == ["UMass Boston"]  # "UMass Boston|UMass Boston" de-duplicated


def test_peopleclick_salary_and_date(http: Http) -> None:
    ps = fetch(board("peopleclick", "client_mit"), http)
    assert_clean(ps)
    first = json.loads((FIX / "peopleclick_jobs.json").read_text())["jobList"][0]["attributes"]
    assert ps[0].title == first["FLD_JP_POSTING_TITLE"]
    if first.get("FLD_JPM_HIRING_RANGE_MIN", "").startswith("$"):
        assert ps[0].salary_min and ps[0].salary_max and ps[0].salary_min <= ps[0].salary_max
    assert ps[0].posted_at is not None


def test_avature_pages_until_repeat_then_reads_detail(http: Http) -> None:
    b = board("avature", "broadinstitute.avature.net")
    ps = fetch(b, http)
    assert_clean(ps)
    assert len(ps) == 5  # 3 on the first page, 2 on the second, then the first page again
    assert all(p.needs_detail and p.source == "avature" for p in ps)
    first = ps[0]
    assert first.url and "/en_US/careers/JobDetail/" in first.url
    assert first.posted_at is not None
    p = enrich(first, b, http)
    assert not p.needs_detail
    assert p.locations == ["Cambridge, MA"]
    assert p.employment_type == "full_time"
    assert (p.salary_min, p.salary_max) == (50_000, 70_000)
    assert p.description and "Computational Associate" in p.description
    assert "Pay Range" not in p.description  # labeled fields stay out of the description
