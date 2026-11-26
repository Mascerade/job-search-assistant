"""Shared data shapes for the job feed."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, TypedDict

from pydantic import BaseModel, Field

# Employer career sites first, then job-board aggregators (listed last so, within a run,
# an employer's own listing is stored before an aggregator's copy of it).
Ats = Literal[
    "greenhouse",
    "lever",
    "ashby",
    "workday",
    "smartrecruiters",
    "jibe",
    "silkroad",
    "pageup",
    "peopleclick",
    "adzuna",
]
Track = Literal["software", "program_admin", "hybrid"]
RemoteType = Literal["onsite", "hybrid", "remote"]
EmploymentType = Literal["full_time", "part_time", "contract", "temporary", "intern"]
PipelineState = Literal["new", "filtered_out"]


class Board(BaseModel):
    """One employer's job board, as listed in config/sources.yaml."""

    ats: Ats
    company: str
    # greenhouse board token / lever company / ashby org / workday tenant / smartrecruiters
    # company id / jibe host / silkroad or pageup short name / peopleclick client code /
    # adzuna place to search around
    token: str
    wd: int | None = None  # workday host number (wd1, wd5, ...)
    site: str | None = None  # workday site name
    feed_url: str | None = None  # RSS feeds (silkroad, pageup)
    search_terms: list[str] = Field(default_factory=list)  # workday, adzuna: search instead of listing all
    # Other names the employer goes by on job boards ("Massachusetts Institute of Technology"
    # for MIT), so aggregator copies of its jobs are recognized and skipped.
    aliases: list[str] = Field(default_factory=list)
    kind: Literal["tech", "university", "hospital", "research", "nonprofit"] = "tech"

    @property
    def key(self) -> str:
        """Stable id for this board, stored as jobs.source_board."""
        return f"{self.ats}:{self.token}" + (f"/{self.site}" if self.site else "")


class Posting(BaseModel):
    """A job posting normalized from any source."""

    source: Ats
    board: str  # Board.key
    native_id: str  # the id at the source
    company: str
    title: str
    url: str | None = None
    locations: list[str] = Field(default_factory=list)
    remote_type: RemoteType | None = None
    employment_type: EmploymentType | None = None
    description: str | None = None  # plain text
    salary_min: int | None = None
    salary_max: int | None = None
    posted_at: datetime | None = None
    needs_detail: bool = False  # Workday list results lack the description

    @property
    def source_job_id(self) -> str:
        # Namespaced by board: ids from different Workday tenants can repeat.
        return f"{self.board.split(':', 1)[1]}:{self.native_id}"

    @property
    def location(self) -> str | None:
        return "; ".join(self.locations) or None


# Tag on postings from staffing / recruiting agencies (see config/staffing_agencies.yaml).
STAFFING_AGENCY_TAG = "staffing-agency"


class JobForScoring(BaseModel):
    id: str
    company: str
    title: str
    location: str | None = None
    remote_type: str | None = None
    employment_type: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    track: Track | None = None
    description: str | None = None
    posted_at: datetime | None = None
    first_seen_at: datetime | None = None
    # Read for the tailoring order; not sent to the AI.
    tags: list[str] = Field(default_factory=list)
    start_kind: str | None = None  # the start window (see timing.py); None = not read yet
    start_from: date | None = None
    start_to: date | None = None

    @property
    def posted_on(self) -> date | None:
        """When the job was posted (or first seen), so the AI can place "this fall"."""
        when = self.posted_at or self.first_seen_at
        return when.date() if when else None


class TrackSettings(BaseModel):
    enabled: bool = True
    keywords: list[str] = Field(default_factory=list)


class LocationSettings(BaseModel):
    include_remote_us: bool = True
    include_hybrid: bool = True
    towns: list[str] = Field(default_factory=list)


class Settings(BaseModel):
    """Mirror of settings.data in the database (edited on the website)."""

    fit_threshold: int = 50
    monthly_spend_cap_usd: float = 40
    tailor_daily_cap: int = 20
    # Until this date, the daily tailoring goes software → hybrid → program admin (see
    # priority.py): university admin roles hire weeks before the start date, and Kojo can't
    # start until after graduating in May 2027. None = always plain best fit first.
    focus_until: date | None = date(2027, 3, 1)
    # The first day Kojo can start a job (after graduating in May 2027). The website's Start
    # column and the tailoring order compare each posting's start window against it.
    available_from: date = date(2027, 6, 1)
    experience_max_years: int = 2
    full_time_only: bool = True
    exclude_clearance: bool = True
    tracks: dict[Track, TrackSettings] = Field(default_factory=dict)
    locations: LocationSettings = Field(default_factory=LocationSettings)


class JobRow(TypedDict):
    """One posting as sent to the ingest_postings database function."""

    source: Ats
    source_job_id: str
    source_board: str
    url: str | None
    company: str
    title: str
    location: str | None
    remote_type: RemoteType | None
    employment_type: EmploymentType | None
    salary_min: int | None
    salary_max: int | None
    description: str | None
    posted_at: str | None  # ISO 8601
    dedupe_key: str
    track: Track | None
    tags: list[str]
    pipeline_state: PipelineState
    filter_reason: str | None
