"""Hard filters: cheap, deterministic rules applied before any AI.

Order (cheapest first):
  1. title_verdict    — does the title match a track, and is it obviously too senior / not full-time?
  2. location_verdict — your Greater Boston towns, US-remote, hybrid
  3. detail_verdict   — needs the description: employment type, clearance, years of experience

Anything borderline is kept; the AI fit score (milestone 3) catches the rest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import EmploymentType, Posting, RemoteType, Settings, Track

TRACK_ORDER: list[Track] = ["software", "program_admin", "hybrid"]


@dataclass
class Verdict:
    keep: bool
    reason: str | None = None  # why it was filtered (short, shown on the website)
    track: Track | None = None
    remote_type: RemoteType | None = None
    tags: list[str] = field(default_factory=list)


def _words(text: str) -> str:
    return re.sub(r"[^a-z0-9+#/]+", " ", text.lower()).strip()


# ---------------------------------------------------------------------------
# 1. Title
# ---------------------------------------------------------------------------


def keyword_matches(keyword: str, title: str) -> bool:
    """Every word of the keyword appears in the title as a word prefix, in any order.

    "program coordinator" matches "Coordinator, Graduate Programs";
    "software engineer" matches "Engineer, Software".
    """
    t = _words(title)
    return all(re.search(rf"\b{re.escape(w)}", t) for w in _words(keyword).split())


# Titles that are never entry-level, for any track.
_ALWAYS_EXCLUDE = [
    r"senior",
    r"sr",
    r"lead",
    r"principal",
    r"director",
    r"head of",
    r"vp",
    r"vice president",
    r"chief",
    r"distinguished",
    r"architect",
    r"iii",
    r"iv",
    r"intern",
    r"internship",
    r"co ?op",
    r"fellow(ship)?",
    r"post ?doc(toral)?",
    r"(assistant |associate |full )?professor",
    r"lecturer",
    r"preceptor",
    r"instructor",
    r"phd",
    r"part ?time",
    r"per diem",
    r"temporary",
    r"temp",
    r"seasonal",
    r"contract(or)?",
    r"volunteer",
    # Clinical roles (hospitals post many "New Graduate Nurse" jobs that would match "new grad")
    r"nurse",
    r"rn",
    r"lpn",
    r"physician",
    r"pharmacist",
    r"surgeon",
    r"dentist",
    r"therapist",
]
# Fine for program-admin titles ("Program Manager", "Staff Assistant"), not for engineering.
_TECH_EXCLUDE = [r"manager", r"staff", r"[345]"]

_ALWAYS_RE = re.compile(r"\b(" + "|".join(_ALWAYS_EXCLUDE) + r")\b")
_TECH_RE = re.compile(r"\b(" + "|".join(_TECH_EXCLUDE) + r")\b")


def title_verdict(title: str, settings: Settings) -> Verdict:
    best: tuple[int, Track] | None = None
    for track in TRACK_ORDER:
        cfg = settings.tracks.get(track)
        if not cfg or not cfg.enabled:
            continue
        for kw in cfg.keywords:
            if keyword_matches(kw, title) and (best is None or len(kw) > best[0]):
                best = (len(kw), track)
    if best is None:
        return Verdict(keep=False, reason="title doesn't match a track")
    track = best[1]
    t = _words(title)
    if m := _ALWAYS_RE.search(t):
        return Verdict(keep=False, reason=f'title: "{m.group(0)}"', track=track)
    if track in ("software", "hybrid") and (m := _TECH_RE.search(t)):
        return Verdict(keep=False, reason=f'title: "{m.group(0)}"', track=track)
    return Verdict(keep=True, track=track)


# ---------------------------------------------------------------------------
# 2. Location
# ---------------------------------------------------------------------------

# Boston neighborhoods and well-known areas that postings use instead of a town name.
_AREAS = [
    "allston", "brighton", "back bay", "beacon hill", "charlestown", "dorchester", "east boston",
    "fenway", "hyde park", "jamaica plain", "kenmore", "longwood", "mattapan", "mission hill",
    "north end", "roslindale", "roxbury", "seaport", "south boston", "south end", "west roxbury",
    "chestnut hill", "kendall square", "harvard square", "greater boston",
]  # fmt: skip
_NON_US = re.compile(
    r"\b(canada|ontario|toronto|vancouver|montreal|quebec|united kingdom|uk|england|london|ireland|dublin|"
    r"europe|emea|germany|berlin|france|paris|netherlands|amsterdam|spain|poland|portugal|india|bangalore|"
    r"bengaluru|hyderabad|apac|singapore|japan|tokyo|australia|sydney|mexico|brazil|latam|argentina|"
    r"colombia|israel|tel aviv|philippines|china|korea)\b"
)
_US = re.compile(r"\b(us|usa|u s|united states|north america|americas|anywhere in the us)\b")
_MA_ONLY = re.compile(r"^(massachusetts|ma)( united states| usa| us)?$")
_MA = re.compile(r"\b(massachusetts|ma)\b")


def location_verdict(posting: Posting, settings: Settings) -> Verdict:
    loc_cfg = settings.locations
    places = [_words(x) for x in posting.locations if x and x.strip()]
    towns = [_words(t) for t in loc_cfg.towns] + _AREAS
    text = " ; ".join(places)
    is_remote = posting.remote_type == "remote" or "remote" in text
    is_hybrid = posting.remote_type == "hybrid" or "hybrid" in text

    def local(place: str) -> bool:
        if _NON_US.search(place):  # "Cambridge, United Kingdom", "Cambridge, Ontario"
            return False
        return any(re.search(rf"\b{re.escape(t)}\b", place) for t in towns)

    if any(local(p) for p in places):
        if is_hybrid and not loc_cfg.include_hybrid:
            return Verdict(keep=False, reason="hybrid jobs are turned off")
        rt: RemoteType = "hybrid" if is_hybrid else (posting.remote_type or "onsite")
        return Verdict(keep=True, remote_type=rt)

    if is_remote:
        remote_places = [p for p in places if "remote" in p] or places
        us_ok = any(_US.search(p) or not _NON_US.search(p) for p in remote_places)
        if not us_ok:
            return Verdict(keep=False, reason="remote, but outside the US")
        if not loc_cfg.include_remote_us:
            return Verdict(keep=False, reason="remote jobs are turned off")
        return Verdict(keep=True, remote_type="remote")

    if not places or all(_MA_ONLY.match(p) for p in places):
        # No usable location (or just "Massachusetts"): keep, flag it.
        return Verdict(keep=True, remote_type=posting.remote_type, tags=["location-unclear"])

    if any(re.fullmatch(r"\d+ locations?", p) for p in places):
        return Verdict(keep=True, remote_type=posting.remote_type, tags=["location-unclear"])

    if any(_MA.search(p) for p in places):
        return Verdict(keep=False, reason="Massachusetts, but outside your towns")
    return Verdict(keep=False, reason="outside the Boston area")


# ---------------------------------------------------------------------------
# 3. Details (need the description)
# ---------------------------------------------------------------------------

_NUM = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_N = r"(\d{1,2}|" + "|".join(_NUM) + r")"
_YEARS = re.compile(rf"\b{_N}\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*{_N}\s*)?\+?\s*(?:years?|yrs?)\b", re.I)
_PREFERRED = re.compile(r"prefer|a plus|is a bonus|ideally|nice to have|desired|desirable", re.I)
_REQUIRED = re.compile(r"\b(required|requires|minimum|must|at least)\b", re.I)
_EXPERIENCE = re.compile(r"experience", re.I)
# "Minimum of four years' post-secondary education or relevant work experience" (Harvard's
# standard wording): a bachelor's degree satisfies it, so it's not a work-experience bar.
_EDUCATION_COUNTS = re.compile(
    r"education,?\s+or\s+(relevant\s+)?(work\s+)?experience|experience\s+or\s+(equivalent\s+)?education"
    r"|equivalent combination of (education|training)",
    re.I,
)


def required_years(description: str | None) -> int | None:
    """Smallest 'N years of experience' the posting *requires* (0 is possible: "0-3 years").

    Skips sentences that only prefer experience, and ones where education counts toward
    the years. Returns None when the posting doesn't state a requirement.
    """
    if not description:
        return None
    found: list[int] = []
    for sentence in re.split(r"(?<=[.;!?])\s+|\n+", description):
        if not _EXPERIENCE.search(sentence) or _EDUCATION_COUNTS.search(sentence):
            continue
        if _PREFERRED.search(sentence) and not _REQUIRED.search(sentence):
            continue
        for m in _YEARS.finditer(sentence):
            raw = m.group(1).lower()
            n = _NUM[raw] if raw in _NUM else int(raw)
            if 0 <= n <= 20:
                found.append(n)
    return min(found) if found else None


_CLEARANCE = re.compile(
    r"\b(security clearance|ts/sci|top secret|secret clearance|active (?:secret |ts )?clearance|"
    r"clearance (?:is )?required|dod clearance|public trust clearance)\b",
    re.I,
)


def detail_verdict(posting: Posting, settings: Settings) -> Verdict:
    if settings.full_time_only and posting.employment_type in (
        "part_time",
        "contract",
        "temporary",
        "intern",
    ):
        return Verdict(keep=False, reason=f"not full-time ({posting.employment_type.replace('_', '-')})")
    if settings.exclude_clearance and posting.description and _CLEARANCE.search(posting.description):
        return Verdict(keep=False, reason="needs a security clearance")
    years = required_years(posting.description)
    # Only obvious mismatches here (5+ for a 2-year limit); 3–4 years is left to the AI score.
    if years is not None and years >= settings.experience_max_years + 3:
        return Verdict(keep=False, reason=f"asks for {years}+ years of experience")
    return Verdict(keep=True)


# ---------------------------------------------------------------------------
# Normalization helpers used by the source adapters
# ---------------------------------------------------------------------------


def normalize_employment(raw: str | None) -> EmploymentType | None:
    if not raw:
        return None
    t = _words(raw).replace(" ", "")
    if "intern" in t or "coop" in t:
        return "intern"
    if "parttime" in t:
        return "part_time"
    if "contract" in t or "freelance" in t:
        return "contract"
    if "temp" in t or "seasonal" in t or "fixedterm" in t:
        return "temporary"
    if "fulltime" in t or "regular" in t or "permanent" in t:
        return "full_time"
    return None


_MONEY = r"\$\s?(\d{2,3}(?:,\d{3})+(?:\.\d{2})?|\d{2,3}(?:\.\d+)?\s?[kK])"
_SALARY = re.compile(_MONEY + r"\s*(?:-|–|—|to)\s*" + _MONEY)


def _money(raw: str) -> float:
    raw = raw.replace(",", "").replace(" ", "")
    return float(raw[:-1]) * 1000 if raw[-1] in "kK" else float(raw)


def salary_from_text(text: str | None) -> tuple[int | None, int | None]:
    """First annual salary range like "$65,000 - $80,000" or "$90k–$120k". Hourly ranges are ignored."""
    if not text:
        return None, None
    for m in _SALARY.finditer(text):
        lo, hi = _money(m.group(1)), _money(m.group(2))
        if lo >= 20_000 and hi >= lo:
            return int(lo), int(hi)
    return None, None


def company_key(name: str) -> str:
    """'The Acme Corp.' and 'Acme, Inc' -> 'acme': the same employer, however it's written."""
    company = re.sub(r"\b(inc|llc|corp|corporation|co|the)\b", "", _words(name)).strip()
    return re.sub(r" +", " ", company)


_AGENCY_WORDS = re.compile(
    r"\b(staffing|recruiting|recruitment|recruiters|personnel|talent solutions|workforce solutions"
    r"|search group)\b"
)
# Agency wording: "Our client is seeking…", "Our client seeks…", "Our client, an industry leader…",
# "on behalf of our client". Consultancies write "our clients" or "our client's needs" instead.
_OUR_CLIENT = re.compile(
    r"\b(?:on behalf of|for) our client\b(?!['’]s)"
    r"|\bour client(?:,| is\b| seeks\b| has\b| needs\b| located\b| based\b| in\b)",
    re.IGNORECASE,
)


def is_staffing_agency(
    company: str, description: str | None, known: frozenset[str], *, read_description: bool
) -> bool:
    """A staffing/recruiting agency posting for another employer?

    `known` holds company_key()s from config/staffing_agencies.yaml; each also matches longer
    names that start with it. The "our client" check is only used for aggregator postings,
    since employer career sites aren't agencies.
    """
    key = company_key(company)
    if any(key == a or key.startswith(a + " ") for a in known):
        return True
    if _AGENCY_WORDS.search(key):
        return True
    return read_description and bool(description and _OUR_CLIENT.search(description))


def dedupe_key(posting: Posting) -> str:
    title = _words(re.split(r"\s[-–|(]\s?", posting.title)[0])  # drop " - Boston", " (Remote)"
    place = _words(posting.locations[0].split(",")[0]) if posting.locations else ""
    return f"{company_key(posting.company)}|{title}|{place}"
