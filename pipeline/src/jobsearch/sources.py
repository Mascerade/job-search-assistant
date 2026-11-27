"""Source adapters: one function per applicant-tracking system.

Each `fetch_*` returns every open posting on a board as `Posting`s (Adzuna, an
aggregator, returns recent search results instead). Workday, SmartRecruiters, and
Avature list pages have no descriptions, so those postings come back with
`needs_detail=True` and `enrich()` fetches the detail page — only for the few that
pass the title and location filters.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup

from .config import ConfigError
from .filters import dedupe_key, normalize_employment, salary_from_text
from .http import Http
from .models import Board, EmploymentType, Posting, RemoteType
from .text import html_to_text

JsonObject = dict[str, Any]  # a decoded JSON object from an API response


def _parse_dt(value: str | int | float | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, int | float):  # epoch milliseconds (Lever)
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _remote(raw: str | None) -> RemoteType | None:
    t = (raw or "").lower().replace("-", "").replace(" ", "")
    if "remote" in t:
        return "remote"
    if "hybrid" in t:
        return "hybrid"
    if "onsite" in t or "inoffice" in t:
        return "onsite"
    return None


def _with_text_salary(p: Posting) -> Posting:
    if p.salary_min is None and p.description:
        p.salary_min, p.salary_max = salary_from_text(p.description)
    return p


# ---------------------------------------------------------------------------
# Greenhouse — https://developers.greenhouse.io/job-board.html
# ---------------------------------------------------------------------------


def fetch_greenhouse(board: Board, http: Http) -> list[Posting]:
    data = http.get_json(
        f"https://boards-api.greenhouse.io/v1/boards/{board.token}/jobs", params={"content": "true"}
    )
    out = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name") or ""
        locations = [x.strip() for x in re.split(r";|\s\|\s", loc) if x.strip()]
        if not locations:
            locations = [o.get("location") or o.get("name") for o in j.get("offices") or [] if o]
        out.append(
            _with_text_salary(
                Posting(
                    source="greenhouse",
                    board=board.key,
                    native_id=str(j["id"]),
                    company=j.get("company_name") or board.company,
                    title=j["title"].strip(),
                    url=j.get("absolute_url"),
                    locations=[x for x in locations if x],
                    remote_type=_remote(loc),
                    description=html_to_text(j.get("content")),
                    posted_at=_parse_dt(j.get("first_published") or j.get("updated_at")),
                )
            )
        )
    return out


# ---------------------------------------------------------------------------
# Lever — https://github.com/lever/postings-api
# ---------------------------------------------------------------------------


def fetch_lever(board: Board, http: Http) -> list[Posting]:
    data = http.get_json(f"https://api.lever.co/v0/postings/{board.token}", params={"mode": "json"})
    out = []
    for j in data:
        cats = j.get("categories") or {}
        locations = cats.get("allLocations") or ([cats["location"]] if cats.get("location") else [])
        parts = [j.get("descriptionPlain") or ""]
        for section in j.get("lists") or []:
            parts.append(f"{section.get('text', '')}\n{html_to_text(section.get('content')) or ''}")
        parts.append(j.get("additionalPlain") or "")
        salary = j.get("salaryRange") or {}
        yearly = (salary.get("interval") or "").lower().startswith("per-year")
        out.append(
            _with_text_salary(
                Posting(
                    source="lever",
                    board=board.key,
                    native_id=j["id"],
                    company=board.company,
                    title=j["text"].strip(),
                    url=j.get("hostedUrl"),
                    locations=locations,
                    remote_type=_remote(j.get("workplaceType")),
                    employment_type=normalize_employment(cats.get("commitment")),
                    description="\n\n".join(p for p in parts if p.strip()).strip() or None,
                    salary_min=int(salary["min"]) if yearly and salary.get("min") else None,
                    salary_max=int(salary["max"]) if yearly and salary.get("max") else None,
                    posted_at=_parse_dt(j.get("createdAt")),
                )
            )
        )
    return out


# ---------------------------------------------------------------------------
# Ashby — https://developers.ashbyhq.com/docs/public-job-posting-api
# ---------------------------------------------------------------------------


def _ashby_salary(comp: JsonObject | None) -> tuple[int | None, int | None]:
    for c in (comp or {}).get("summaryComponents") or []:
        if c.get("compensationType") == "Salary" and "YEAR" in (c.get("interval") or "").upper():
            lo, hi = c.get("minValue"), c.get("maxValue")
            if lo and hi:
                return int(lo), int(hi)
    return None, None


def fetch_ashby(board: Board, http: Http) -> list[Posting]:
    data = http.get_json(
        f"https://api.ashbyhq.com/posting-api/job-board/{board.token}", params={"includeCompensation": "true"}
    )
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        locations = [j.get("location")] + [s.get("location") for s in j.get("secondaryLocations") or []]
        lo, hi = _ashby_salary(j.get("compensation"))
        remote = _remote(j.get("workplaceType")) or ("remote" if j.get("isRemote") else None)
        out.append(
            _with_text_salary(
                Posting(
                    source="ashby",
                    board=board.key,
                    native_id=j["id"],
                    company=board.company,
                    title=j["title"].strip(),
                    url=j.get("jobUrl") or j.get("applyUrl"),
                    locations=[x for x in locations if x],
                    remote_type=remote,
                    employment_type=normalize_employment(j.get("employmentType")),
                    description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
                    salary_min=lo,
                    salary_max=hi,
                    posted_at=_parse_dt(j.get("publishedAt")),
                )
            )
        )
    return out


# ---------------------------------------------------------------------------
# Workday (unofficial "cxs" endpoints used by every myworkdayjobs.com site)
# ---------------------------------------------------------------------------

WORKDAY_PAGE = 20  # the list endpoint rejects larger pages (HTTP 400)
WORKDAY_MAX = 2000  # Workday stops at 2000; larger offsets silently return page 1 again


def _workday_base(board: Board) -> str:
    return f"https://{board.token}.wd{board.wd}.myworkdayjobs.com"


def _workday_posted(text: str | None, now: datetime | None = None) -> datetime | None:
    """ "Posted Today" / "Posted Yesterday" / "Posted 3 Days Ago" / "Posted 30+ Days Ago"."""
    if not text:
        return None
    now = now or datetime.now(UTC)
    t = text.lower()
    if "today" in t:
        return now
    if "yesterday" in t:
        return now - timedelta(days=1)
    if m := re.search(r"(\d+)\+?\s*days?", t):
        return now - timedelta(days=int(m.group(1)))
    return None


def _workday_search(board: Board, http: Http, search_text: str) -> list[JsonObject]:
    url = f"{_workday_base(board)}/wday/cxs/{board.token}/{board.site}/jobs"
    items: list[JsonObject] = []
    total: int | None = None
    offset = 0
    while offset < WORKDAY_MAX:
        body = {"limit": WORKDAY_PAGE, "offset": offset, "searchText": search_text, "appliedFacets": {}}
        data = http.post_json(url, body)
        if total is None:
            total = data.get("total") or 0  # only reliable on the first page
        page = data.get("jobPostings") or []
        items.extend(page)
        offset += WORKDAY_PAGE
        if len(page) < WORKDAY_PAGE or offset >= total:
            break
    return items


def fetch_workday(board: Board, http: Http) -> list[Posting]:
    if not board.wd or not board.site:
        raise ValueError(f"Workday board {board.company} needs wd and site")
    # Huge tenants (hospital systems with 2000+ openings) are searched by keyword instead.
    raw: dict[str, JsonObject] = {}
    for term in board.search_terms or [""]:
        for j in _workday_search(board, http, term):
            if j.get("externalPath"):
                raw.setdefault(j["externalPath"], j)
    base = _workday_base(board)
    out = []
    for path, j in raw.items():
        if not j.get("title"):
            continue
        loc = j.get("locationsText") or ""
        out.append(
            Posting(
                source="workday",
                board=board.key,
                native_id=path.rsplit("/", 1)[-1],
                company=board.company,
                title=j["title"].strip(),
                url=f"{base}/{board.site}{path}",
                locations=[loc] if loc else [],
                remote_type=_remote(loc),
                employment_type=normalize_employment(j.get("timeType")),
                posted_at=_workday_posted(j.get("postedOn")),
                needs_detail=True,
            )
        )
    return out


def enrich_workday(p: Posting, board: Board, http: Http) -> Posting:
    path = p.url.split(f"/{board.site}", 1)[1] if p.url else None
    if not path:
        return p
    data = http.get_json(f"{_workday_base(board)}/wday/cxs/{board.token}/{board.site}{path}")
    info = data.get("jobPostingInfo") or {}
    locations = [info.get("location")] + list(info.get("additionalLocations") or [])
    p.locations = [x for x in locations if x] or p.locations
    p.description = html_to_text(info.get("jobDescription"))
    p.employment_type = normalize_employment(info.get("timeType")) or p.employment_type
    p.remote_type = _remote(info.get("remoteType")) or _remote(" ".join(p.locations)) or p.remote_type
    p.posted_at = _parse_dt(info.get("startDate")) or p.posted_at  # the real posting date
    p.url = info.get("externalUrl") or p.url
    p.needs_detail = False
    return _with_text_salary(p)


# ---------------------------------------------------------------------------
# SmartRecruiters (Harvard) — https://dev.smartrecruiters.com/customer-api/posting-api/
# ---------------------------------------------------------------------------


def fetch_smartrecruiters(board: Board, http: Http) -> list[Posting]:
    url = f"https://api.smartrecruiters.com/v1/companies/{board.token}/postings"
    out: list[Posting] = []
    offset = 0
    while True:
        data = http.get_json(url, params={"limit": 100, "offset": offset})
        page = data.get("content") or []
        for j in page:
            loc = j.get("location") or {}
            remote: RemoteType | None = (
                "remote" if loc.get("remote") else "hybrid" if loc.get("hybrid") else None
            )
            out.append(
                Posting(
                    source="smartrecruiters",
                    board=board.key,
                    native_id=str(j["id"]),
                    company=board.company,
                    title=j["name"].strip(),
                    url=f"https://jobs.smartrecruiters.com/{board.token}/{j['id']}",
                    locations=[loc["fullLocation"]] if loc.get("fullLocation") else [],
                    remote_type=remote,
                    employment_type=normalize_employment((j.get("typeOfEmployment") or {}).get("label")),
                    posted_at=_parse_dt(j.get("releasedDate")),
                    needs_detail=True,
                )
            )
        offset += len(page)
        if not page or offset >= (data.get("totalFound") or 0):
            return out


def enrich_smartrecruiters(p: Posting, board: Board, http: Http) -> Posting:
    data = http.get_json(f"https://api.smartrecruiters.com/v1/companies/{board.token}/postings/{p.native_id}")
    sections = (data.get("jobAd") or {}).get("sections") or {}
    parts = [
        html_to_text((sections.get(k) or {}).get("text"))
        for k in (
            "jobDescription",
            "qualifications",
            "additionalInformation",
        )  # skip the boilerplate "about us"
    ]
    p.description = "\n\n".join(x for x in parts if x) or None
    p.url = data.get("postingUrl") or p.url
    p.needs_detail = False
    return _with_text_salary(p)


# ---------------------------------------------------------------------------
# Jibe career sites on iCIMS (Tufts): https://{host}/api/jobs
# ---------------------------------------------------------------------------


def fetch_jibe(board: Board, http: Http) -> list[Posting]:
    host = board.token
    out: list[Posting] = []
    page = 1
    while True:
        data = http.get_json(f"https://{host}/api/jobs", params={"page": page, "limit": 100})
        jobs = [j.get("data") or {} for j in data.get("jobs") or []]
        for j in jobs:
            tags = " ".join(str(j.get(k) or "") for k in ("tags1", "tags3"))
            parts = [html_to_text(j.get(k)) for k in ("description", "responsibilities", "qualifications")]
            out.append(
                _with_text_salary(
                    Posting(
                        source="jibe",
                        board=board.key,
                        native_id=str(j.get("req_id") or j.get("slug")),
                        company=board.company,
                        title=(j.get("title") or "").strip(),
                        url=f"https://{host}/jobs/{j.get('slug') or j.get('req_id')}",
                        locations=[j.get("full_location") or j.get("short_location") or ""],
                        remote_type=_remote(tags),
                        employment_type=normalize_employment(j.get("employment_type")),
                        description="\n\n".join(x for x in parts if x) or None,
                        posted_at=_parse_dt((j.get("posted_date") or "").replace("+0000", "+00:00")),
                    )
                )
            )
        if not jobs or len(out) >= (data.get("totalCount") or 0):
            return [p for p in out if p.title]
        page += 1


# ---------------------------------------------------------------------------
# RSS feeds: SilkRoad (BU) and PageUp (UMass Boston)
# ---------------------------------------------------------------------------

_PAGEUP_NS = "{http://pageuppeople.com/}"


def _rss_items(http: Http, url: str) -> list[ET.Element]:
    resp = http.request("GET", url, headers={"Accept": "application/rss+xml, application/xml"})
    return ET.fromstring(resp.content).findall(".//item")


def _text(item: ET.Element, tag: str) -> str:
    el = item.find(tag)
    return (el.text or "").strip() if el is not None else ""


def _fix_caps(title: str) -> str:
    """BU titles arrive as "SENIOR SECURITY ASSISTANT, Office of Housing"; tame the shouting."""
    return " ".join(w.capitalize() if w.isupper() and len(w) > 3 else w for w in title.split())


def _salary_field(raw: str) -> int | None:
    try:
        value = float(raw.replace("$", "").replace(",", "").strip())
    except ValueError:
        return None
    return int(value) if value >= 20_000 else None  # skip hourly rates


def fetch_silkroad(board: Board, http: Http) -> list[Posting]:
    out = []
    for item in _rss_items(http, board.feed_url or f"https://jobs.silkroad.com/{board.token}/External/rss"):
        link = _text(item, "link")
        parts = [
            html_to_text(_text(item, k)) for k in ("jobDescription", "requiredSkills", "requiredExperience")
        ]
        lo, hi = _salary_field(_text(item, "minSalary")), _salary_field(_text(item, "maxSalary"))
        out.append(
            _with_text_salary(
                Posting(
                    source="silkroad",
                    board=board.key,
                    native_id=link.rstrip("/").rsplit("/", 1)[-1],
                    company=board.company,
                    title=_fix_caps(_text(item, "title")),
                    url=link,
                    locations=[_text(item, "location")] if _text(item, "location") else [],
                    employment_type=normalize_employment(_text(item, "position")),
                    description="\n\n".join(x for x in parts if x) or None,
                    salary_min=lo if lo and hi else None,
                    salary_max=hi if lo and hi else None,
                    posted_at=_parse_rfc822(_text(item, "postingDate")),
                )
            )
        )
    return out


def fetch_pageup(board: Board, http: Http) -> list[Posting]:
    out = []
    for item in _rss_items(http, board.feed_url or ""):
        locs = {x.strip() for x in _text(item, f"{_PAGEUP_NS}location").split("|") if x.strip()}
        out.append(
            _with_text_salary(
                Posting(
                    source="pageup",
                    board=board.key,
                    native_id=_text(item, f"{_PAGEUP_NS}refNo") or _text(item, "link").rsplit("/", 1)[-1],
                    company=board.company,
                    title=_text(item, "title"),
                    url=_text(item, "link"),
                    locations=sorted(locs),
                    employment_type=normalize_employment(_text(item, f"{_PAGEUP_NS}workType")),
                    description=html_to_text(
                        _text(item, f"{_PAGEUP_NS}description") or _text(item, "description")
                    ),
                    posted_at=_parse_rfc822(_text(item, "pubDate")),
                )
            )
        )
    return out


def _parse_rfc822(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw.replace(" Z", " +0000"))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# Peopleclick (MIT): needs a session cookie from the search page first
# ---------------------------------------------------------------------------


def fetch_peopleclick(board: Board, http: Http) -> list[Posting]:
    client = board.token  # e.g. "client_mit"
    site = f"https://careers.peopleclick.com/careerscp/{client}/external"
    http.request("GET", f"{site}/search.do")  # sets the session cookie
    http.request("GET", f"{site}/results/searchResult.html")
    api = f"https://careers.peopleclick.com/careerscp/api/{client}/external/en-US/getJobs"
    out: list[Posting] = []
    page = 1
    while True:
        data = http.get_json(api, params={"page": page})
        jobs = data.get("jobList") or []
        for j in jobs:
            a = j.get("attributes") or {}
            post_id = j.get("jobPostId")
            parts = [html_to_text(a.get("JPM_DESCRIPTION")), html_to_text(a.get("JPM_ESSENTIALFUNCTIONS"))]
            lo, hi = (
                _salary_field(a.get(k) or "")
                for k in ("FLD_JPM_HIRING_RANGE_MIN", "FLD_JPM_HIRING_RANGE_MAX")
            )
            out.append(
                _with_text_salary(
                    Posting(
                        source="peopleclick",
                        board=board.key,
                        native_id=str(post_id),
                        company=board.company,
                        title=(a.get("FLD_JP_POSTING_TITLE") or a.get("JPM_TITLE") or "").strip(),
                        url=f"{site}/jobDetails/jobDetail.html?jobPostId={post_id}&localeCode=en-us",
                        locations=[a["JPM_LOCATION"]] if a.get("JPM_LOCATION") else [],
                        remote_type=_remote(a.get("JPM_WORKENVIRONMENT")),
                        employment_type=normalize_employment(a.get("JPM_DURATION")),
                        description="\n\n".join(x for x in parts if x) or None,
                        salary_min=lo if lo and hi else None,
                        salary_max=hi if lo and hi else None,
                        posted_at=_parse_peopleclick_date(a.get("JP_POSTEDON")),
                    )
                )
            )
        if not jobs or page * (data.get("hitsPerPage") or 50) >= (data.get("totalHits") or 0):
            return [p for p in out if p.title]
        page += 1


def _parse_peopleclick_date(raw: str | None) -> datetime | None:
    try:
        return datetime.strptime(raw or "", "%b %d, %Y").replace(tzinfo=UTC)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Avature career sites (Broad Institute): server-rendered HTML, no API.
# The list pages (6 jobs each, whatever page size is asked for) have the title, posted
# date, and work mode; the location, pay, and description are on each job's page, so
# postings come back with needs_detail=True. Avature's RSS feed stops at 20 jobs.
# ---------------------------------------------------------------------------

AVATURE_MAX_PAGES = 100  # 600 jobs; Broad lists about 40
_AVATURE_ID = re.compile(r"/JobDetail/[^/?#]+/(\d+)")
_HTML = {"Accept": "text/html"}


def _avature_base(board: Board) -> str:
    return f"https://{board.token}/{board.site or 'en_US/careers'}"


def _avature_posted(raw: str) -> datetime | None:
    try:  # "Posted 25-Nov-2026"
        return datetime.strptime(raw.replace("Posted", "").strip(), "%d-%b-%Y").replace(tzinfo=UTC)
    except ValueError:
        return None


def parse_avature_list(board: Board, page: str) -> list[Posting]:
    out = []
    for item in BeautifulSoup(page, "html.parser").select("article.article--result"):
        link = item.select_one(".article__header__text__title a[href]")
        m = _AVATURE_ID.search(str(link.get("href"))) if link else None
        if not link or not m:
            continue
        posted = item.select_one(".list-item-posted")
        workplace = item.select_one(".list-item-workplace")
        out.append(
            Posting(
                source="avature",
                board=board.key,
                native_id=m.group(1),
                company=board.company,
                title=" ".join(link.get_text().split()),
                url=str(link["href"]),
                remote_type=_remote(workplace.get_text() if workplace else None),
                posted_at=_avature_posted(posted.get_text()) if posted else None,
                needs_detail=True,
            )
        )
    return out


def fetch_avature(board: Board, http: Http) -> list[Posting]:
    found: dict[str, Posting] = {}
    offset = 0
    for _ in range(AVATURE_MAX_PAGES):
        page = http.request(
            "GET", f"{_avature_base(board)}/SearchJobs/", params={"jobOffset": offset}, headers=_HTML
        ).text
        listed = parse_avature_list(board, page)
        new = [p for p in listed if p.native_id not in found]
        if not new:  # past the end, Avature repeats the last page
            break
        found.update((p.native_id, p) for p in new)
        offset += len(listed)
    return list(found.values())


def _avature_pay(raw: str) -> tuple[int | None, int | None]:
    """ "$50,000.00/yr - $70,000.00/yr" (hourly ranges are ignored)."""
    if "/hr" in raw.lower() or "hour" in raw.lower():
        return None, None
    return salary_from_text(re.sub(r"\s*/\s*(yr|year)", "", raw, flags=re.I))


def parse_avature_detail(p: Posting, page: str) -> Posting:
    fields: dict[str, str] = {}
    body: list[str] = []
    for f in BeautifulSoup(page, "html.parser").select(".article__content__view__field"):
        label = f.select_one(".article__content__view__field__label")
        value = f.select_one(".article__content__view__field__value")
        if label:
            fields[label.get_text(" ", strip=True).lower()] = value.get_text(" ", strip=True) if value else ""
        elif text := html_to_text(str(f)):
            body.append(text)
    if loc := fields.get("location"):
        p.locations = [x.strip() for x in loc.split(";") if x.strip()]
    p.employment_type = normalize_employment(fields.get("time type")) or p.employment_type
    p.salary_min, p.salary_max = _avature_pay(fields.get("pay range", ""))
    p.description = "\n\n".join(body) or p.description
    p.needs_detail = False
    return _with_text_salary(p)


def enrich_avature(p: Posting, board: Board, http: Http) -> Posting:
    if not p.url:
        return p
    return parse_avature_detail(p, http.request("GET", p.url, headers=_HTML).text)


# ---------------------------------------------------------------------------
# Adzuna — https://developer.adzuna.com/docs/search (a job-board aggregator)
#
# One "board" is a set of title searches around one place (Board.token, e.g. "Boston").
# Two differences from employer sites, handled in daily.py:
#   - Adzuna returns only a snippet of each description (jobs get a "short-description" tag).
#   - The results are a recent-postings window, not a full list, so a job missing from
#     today's results is NOT marked closed.
# The API keys travel in the URL, so errors are re-raised without it.
# ---------------------------------------------------------------------------

ADZUNA_SEARCH = "https://api.adzuna.com/v1/api/jobs/us/search/{page}"
ADZUNA_PAGE = 50
ADZUNA_MAX_PAGES = 2  # per search term
ADZUNA_MAX_DAYS_OLD = 14
ADZUNA_DISTANCE = 25  # miles around Board.token (checked live); the town filter does the precise cut

_ADZUNA_EMPLOYMENT: dict[str, EmploymentType] = {
    "full_time": "full_time",
    "part_time": "part_time",
    "contract": "contract",
}


class AdzunaError(RuntimeError):
    """An Adzuna request failed (message never includes the URL, which holds the keys)."""


def adzuna_keys() -> tuple[str, str]:
    app_id = os.environ.get("ADZUNA_APP_ID", "").strip()
    app_key = os.environ.get("ADZUNA_APP_KEY", "").strip()
    if not app_id or not app_key:
        raise ConfigError(
            "ADZUNA_APP_ID / ADZUNA_APP_KEY aren't set (pipeline/.env.production and GitHub secrets)."
        )
    return app_id, app_key


def _one_line(raw: str | None) -> str:
    return " ".join((html_to_text(raw) or "").split())


def _whole_dollars(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) and value > 0 else None


def _adzuna_posting(board: Board, r: JsonObject) -> Posting | None:
    title = _one_line(r.get("title"))
    company = _one_line((r.get("company") or {}).get("display_name"))
    native_id = str(r.get("id") or "")
    if not (title and company and native_id):
        return None
    loc = r.get("location") or {}
    # area runs country → state → county → town (→ neighborhood): ["US", "Massachusetts",
    # "Middlesex County", "Cambridge"]. Most specific first keeps the town in the string even
    # when display_name is just a neighborhood ("Harvard Square, Middlesex County").
    area = [a.strip() for a in loc.get("area") or [] if isinstance(a, str) and a.strip()]
    place = ", ".join(reversed(area[1:])) if len(area) >= 2 else _one_line(loc.get("display_name"))
    predicted = str(r.get("salary_is_predicted") or "0") == "1"  # Adzuna's own estimate: ignore
    return Posting(
        source="adzuna",
        board=board.key,
        native_id=native_id,
        company=company,
        title=title,
        url=r.get("redirect_url"),
        locations=[place] if place else [],
        remote_type=_remote(title),
        employment_type=_ADZUNA_EMPLOYMENT.get(r.get("contract_time") or "")
        or _ADZUNA_EMPLOYMENT.get(r.get("contract_type") or ""),
        description=html_to_text(r.get("description")),
        salary_min=None if predicted else _whole_dollars(r.get("salary_min")),
        salary_max=None if predicted else _whole_dollars(r.get("salary_max")),
        posted_at=_parse_dt(r.get("created")),
    )


def fetch_adzuna(board: Board, http: Http) -> list[Posting]:
    app_id, app_key = adzuna_keys()
    found: dict[str, Posting] = {}
    same_job: set[str] = set()  # Adzuna often lists one job several times under different ids
    for term in board.search_terms:
        for page in range(1, ADZUNA_MAX_PAGES + 1):
            params: dict[str, str | int] = {
                "app_id": app_id,
                "app_key": app_key,
                "results_per_page": ADZUNA_PAGE,
                "title_only": term,
                "where": board.token,
                "distance": ADZUNA_DISTANCE,
                "max_days_old": ADZUNA_MAX_DAYS_OLD,
                "sort_by": "date",
            }
            try:
                data = http.get_json(ADZUNA_SEARCH.format(page=page), params=params)
            except httpx.HTTPStatusError as e:
                raise AdzunaError(f"HTTP {e.response.status_code} searching '{term}'") from None
            results = data.get("results") or []
            for r in results:
                p = _adzuna_posting(board, r)
                if p is None or p.native_id in found or dedupe_key(p) in same_job:
                    continue
                found[p.native_id] = p
                same_job.add(dedupe_key(p))
            if len(results) < ADZUNA_PAGE:
                break
    return list(found.values())


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

FETCHERS: dict[str, Callable[[Board, Http], list[Posting]]] = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "workday": fetch_workday,
    "smartrecruiters": fetch_smartrecruiters,
    "jibe": fetch_jibe,
    "silkroad": fetch_silkroad,
    "pageup": fetch_pageup,
    "peopleclick": fetch_peopleclick,
    "avature": fetch_avature,
    "adzuna": fetch_adzuna,
}

ENRICHERS: dict[str, Callable[[Posting, Board, Http], Posting]] = {
    "workday": enrich_workday,
    "smartrecruiters": enrich_smartrecruiters,
    "avature": enrich_avature,
}


def fetch(board: Board, http: Http) -> list[Posting]:
    return FETCHERS[board.ats](board, http)


def enrich(p: Posting, board: Board, http: Http) -> Posting:
    if p.needs_detail and board.ats in ENRICHERS:
        return ENRICHERS[board.ats](p, board, http)
    return p
