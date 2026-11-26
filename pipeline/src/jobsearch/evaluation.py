"""Evaluation set for fit scoring.

Kojo labels ~40 real postings yes / maybe / no *without seeing the AI's scores*
(private/eval/scoring_labels.yaml, gitignored). The report scores them fresh and
shows, for each possible threshold, how many good jobs it would catch (recall)
and how much noise it would let through (precision), plus the disagreements.

    uv run jobsearch eval export          # write the labeling file
    uv run jobsearch eval report          # after labeling: metrics + suggested threshold
"""

from __future__ import annotations

import random
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, field_validator

from .config import REPO_DIR
from .models import JobForScoring

Label = Literal["yes", "maybe", "no"]
LABELS_FILE = REPO_DIR / "private" / "eval" / "scoring_labels.yaml"
THRESHOLDS = list(range(30, 90, 5))

HEADER = """\
# Fit-scoring evaluation set — label each job, then run: uv run jobsearch eval report
#
# For each job set `label` to one of:
#   yes   = I'd want this in my matches (I'd consider applying)
#   maybe = borderline; fine either way
#   no    = I wouldn't want to see this
# Judge from the title/snippet, or open the link. Optional: add a short `note` on why.
# Don't worry about consistency or speed; your gut reaction is what we're measuring.
"""


class EvalItem(BaseModel):
    job_id: str
    company: str
    title: str
    location: str | None = None
    url: str | None = None
    snippet: str = ""
    label: Label | None = None
    note: str = ""

    @field_validator("label", mode="before")
    @classmethod
    def _normalize_label(cls, v: object) -> object:
        # YAML reads a bare `yes` / `no` as true / false (the "Norway problem").
        if v is True:
            return "yes"
        if v is False:
            return "no"
        if isinstance(v, str):
            t = v.strip().lower()
            return {"y": "yes", "n": "no", "m": "maybe", "": None}.get(t, t)
        return v

    @field_validator("note", mode="before")
    @classmethod
    def _note_text(cls, v: object) -> object:
        return "" if v is None else str(v)


def sample(jobs: Sequence[JobForScoring], n: int, seed: int = 7) -> list[JobForScoring]:
    """A reproducible sample, spread across tracks in proportion to how common they are."""
    by_track: dict[str, list[JobForScoring]] = defaultdict(list)
    for j in jobs:
        by_track[j.track or "unknown"].append(j)
    rng = random.Random(seed)
    picked: list[JobForScoring] = []
    for track in sorted(by_track):
        group = sorted(by_track[track], key=lambda j: j.id)
        quota = max(1, round(n * len(group) / max(len(jobs), 1)))
        picked.extend(rng.sample(group, min(quota, len(group))))
    rng.shuffle(picked)
    return picked[:n]


_ROLE_MARKERS = re.compile(
    r"(what you'?ll do|what you will do|responsibilities|the role|about the role|position summary|"
    r"job summary|position description|job description|duties|overview of the position|you will)",
    re.I,
)


def snippet(description: str | None, length: int = 400) -> str:
    """The start of the *role* description, skipping company boilerplate when possible."""
    text = " ".join((description or "").split())
    m = _ROLE_MARKERS.search(text, 0, 4000)
    start = m.start() if m and m.start() > 80 else 0
    out = text[start : start + length]
    return out + ("…" if len(text) > start + length else "")


def to_items(jobs: Sequence[JobForScoring], urls: dict[str, str | None]) -> list[EvalItem]:
    items = []
    for j in jobs:
        snippet_text = snippet(j.description)
        items.append(
            EvalItem(job_id=j.id, company=j.company, title=j.title, location=j.location,
                     url=urls.get(j.id), snippet=snippet_text)
        )  # fmt: skip
    return items


def write_labels_file(items: Sequence[EvalItem], path: Path = LABELS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(
        [i.model_dump(mode="json") for i in items], sort_keys=False, allow_unicode=True, width=100
    )
    path.write_text(HEADER + "\n" + body)


def read_labels_file(path: Path = LABELS_FILE) -> list[EvalItem]:
    raw = yaml.safe_load(path.read_text()) or []
    return [EvalItem.model_validate(r) for r in raw]


@dataclass(frozen=True)
class ThresholdRow:
    threshold: int
    shown: int  # jobs at or above the threshold
    precision: float  # share of shown jobs you labeled yes/maybe
    recall: float  # share of yes/maybe jobs that are shown
    recall_yes: float  # share of "yes" jobs that are shown


def metrics(pairs: Sequence[tuple[Label, int]], thresholds: Sequence[int] = THRESHOLDS) -> list[ThresholdRow]:
    rows = []
    positives = [s for label, s in pairs if label in ("yes", "maybe")]
    yeses = [s for label, s in pairs if label == "yes"]
    for t in thresholds:
        shown = [(label, s) for label, s in pairs if s >= t]
        good_shown = sum(1 for label, _ in shown if label in ("yes", "maybe"))
        rows.append(
            ThresholdRow(
                threshold=t,
                shown=len(shown),
                precision=good_shown / len(shown) if shown else 1.0,
                recall=sum(1 for s in positives if s >= t) / len(positives) if positives else 1.0,
                recall_yes=sum(1 for s in yeses if s >= t) / len(yeses) if yeses else 1.0,
            )
        )
    return rows


def suggest_threshold(rows: Sequence[ThresholdRow], min_recall_yes: float = 0.9) -> int:
    """Highest threshold that still shows ≥90% of your "yes" jobs (missing good jobs is worse
    than seeing a few extra)."""
    ok = [r for r in rows if r.recall_yes >= min_recall_yes]
    return max(ok, key=lambda r: r.threshold).threshold if ok else min(r.threshold for r in rows)
