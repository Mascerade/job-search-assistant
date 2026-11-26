"""Which matches get the day's resumes and cover letters first (the daily cap is 20).

Order, best fit first within each group:

  1. Postings tied to a future start (a "2027 new grad" program): the timing fits exactly.
  2. Until Settings.focus_until (default March 1, 2027):
       software → hybrid (university tech) → program admin.
     Software employers hire new grads months ahead; university and nonprofit admin roles
     usually hire a few weeks before the start date, and Kojo can't start until after
     graduating in May 2027. Admin matches stay visible on the site and can be tailored
     anytime with "Tailor now"; they just don't use up the automatic daily slots yet.
     After the date: plain best fit first.
  3. Staffing-agency postings come after all direct-employer jobs, always.
"""

from __future__ import annotations

from datetime import date

from .models import FUTURE_START_TAG, STAFFING_AGENCY_TAG, JobForScoring, Settings

FOCUS_TRACK_RANK = {"software": 1, "hybrid": 2, "program_admin": 3}


def in_focus_window(settings: Settings, today: date | None = None) -> bool:
    today = today or date.today()
    return settings.focus_until is not None and today < settings.focus_until


def tailoring_order(
    jobs: list[JobForScoring], settings: Settings, today: date | None = None
) -> list[JobForScoring]:
    """`jobs` arrive best fit first; returns them in the order they should be tailored."""
    focus = in_focus_window(settings, today)

    def rank(j: JobForScoring) -> tuple[bool, int]:
        agency = STAFFING_AGENCY_TAG in j.tags
        right_timing = FUTURE_START_TAG in j.tags or not focus
        return (agency, 0 if right_timing else FOCUS_TRACK_RANK.get(j.track or "", 2))

    return sorted(jobs, key=rank)  # sorted() is stable: best fit first within each group
