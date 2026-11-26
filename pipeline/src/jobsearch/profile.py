"""The master profile: the only source of facts the tailoring step may use.

Every resume bullet the AI writes must cite the `id` of the fact(s) it came from.
Anything it can't cite becomes a *suggestion* that Kojo approves or rejects.

The website's validator (web/src/lib/profile.ts) mirrors these rules.

`application` holds Kojo's standard answers for job application forms (apply assist,
milestone 6). It is only used to fill forms: never sent to the AI that scores or writes.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

PLACEHOLDER = re.compile(r"\[[^\]]*\]")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Fact(Strict):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    text: str = Field(min_length=1)
    tags: list[str] = []


class Entry(Strict):
    """An experience or project, with the facts (bullets) that describe it."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str | None = None  # role title (experience)
    org: str | None = None  # employer (experience)
    name: str | None = None  # project name
    location: str | None = None
    start: str | None = None
    end: str | None = None
    stack: list[str] = []
    facts: list[Fact]


class Contact(Strict):
    name: str
    email: str
    phone: str | None = None
    location: str | None = None
    links: list[str] = []


class Education(Strict):
    id: str
    school: str
    degree: str
    location: str | None = None
    end: str
    details: list[str] = []


class SkillGroup(Strict):
    category: str
    items: list[str]


def normalize_question(question: str) -> str:
    """ "Are you 18 or older?" and "are you 18 or older" are the same question."""
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", question.lower()).split())


class QA(Strict):
    """A recurring application question and the answer Kojo approved for it."""

    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)


class Demographics(Strict):
    """Kojo's choices for voluntary self-identification questions (may be "Decline to self-identify")."""

    gender: str | None = None
    race_ethnicity: str | None = None
    hispanic_latino: str | None = None
    veteran: str | None = None
    disability: str | None = None


class ApplicationLinks(Strict):
    """Overrides for links that forms ask for by name; defaults come from contact.links."""

    linkedin: str | None = None
    github: str | None = None
    website: str | None = None
    portfolio: str | None = None


class ApplicationAnswers(Strict):
    """Standard answers for application forms. None means "ask Kojo on each form"."""

    # YAML reads `gpa: 3.7` or `salary_expectation: 85000` as numbers; keep them as text.
    model_config = ConfigDict(extra="forbid", coerce_numbers_to_str=True)

    work_authorized_us: bool | None = None
    sponsorship_now: bool | None = None
    sponsorship_future: bool | None = None
    over_18: bool | None = None
    preferred_name: str | None = None
    pronouns: str | None = None
    address: str | None = None
    gpa: str | None = None
    salary_expectation: str | None = None
    willing_to_relocate: bool | None = None
    how_heard: str | None = None
    links: ApplicationLinks = Field(default_factory=ApplicationLinks)
    demographics: Demographics = Field(default_factory=Demographics)
    custom: list[QA] = []

    @model_validator(mode="after")
    def _one_answer_per_question(self) -> ApplicationAnswers:
        latest: dict[str, QA] = {}
        for qa in self.custom:  # a later answer to the same question wins
            latest[normalize_question(qa.question)] = qa
        self.custom = list(latest.values())
        return self

    def answer_for(self, question: str) -> str | None:
        key = normalize_question(question)
        return next((qa.answer for qa in self.custom if normalize_question(qa.question) == key), None)


class Profile(Strict):
    contact: Contact
    summaries: dict[str, str] = {}
    education: list[Education]
    experience: list[Entry]
    projects: list[Entry]
    skills: list[SkillGroup]
    certifications: list[str] = []
    extra_facts: list[Fact] = []
    declined_skills: list[str] = []  # skills Kojo said no to; never suggested again
    application: ApplicationAnswers | None = None  # apply assist only; never sent to the AI

    @model_validator(mode="after")
    def _check_facts(self) -> Profile:
        seen: set[str] = set()
        problems: list[str] = []
        for fact in self.all_facts():
            if fact.id in seen:
                problems.append(f'duplicate fact id "{fact.id}"')
            seen.add(fact.id)
            if PLACEHOLDER.search(fact.text):
                problems.append(f"{fact.id}: remove the [placeholder] or fill it in")
        for text in [*self.summaries.values(), *(d for e in self.education for d in e.details)]:
            if PLACEHOLDER.search(text):
                problems.append(f'remove the [placeholder] in: "{text[:60]}"')
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def all_facts(self) -> list[Fact]:
        return [f for e in [*self.experience, *self.projects] for f in e.facts] + list(self.extra_facts)

    def fact_index(self) -> dict[str, Fact]:
        return {f.id: f for f in self.all_facts()}

    def all_skills(self) -> set[str]:
        return {item.lower() for group in self.skills for item in group.items}

    def add_skill(self, skill: str, category: str) -> bool:
        """Add a skill under `category` (or the first group if that category doesn't exist).
        Returns False if the profile already has it."""
        if skill.lower() in self.all_skills():
            return False
        group = next((g for g in self.skills if g.category.lower() == category.lower()), None)
        if group is None:
            group = self.skills[0] if self.skills else None
        if group is None:
            self.skills.append(SkillGroup(category=category or "Skills", items=[skill]))
        else:
            group.items.append(skill)
        self.declined_skills = [s for s in self.declined_skills if s.lower() != skill.lower()]
        return True

    def decline_skill(self, skill: str) -> None:
        if skill.lower() not in {s.lower() for s in self.declined_skills}:
            self.declined_skills.append(skill)

    def remember_answer(self, question: str, answer: str, *, replace: bool = False) -> bool:
        """Save a recurring question's answer. Returns False if the question already has a
        different answer and `replace` is off."""
        answers = self.application or ApplicationAnswers()
        existing = answers.answer_for(question)
        if existing is not None and existing != answer and not replace:
            return False
        key = normalize_question(question)
        custom = [qa for qa in answers.custom if normalize_question(qa.question) != key]
        custom.append(QA(question=question.strip(), answer=answer.strip()))
        self.application = answers.model_copy(update={"custom": custom})
        return True


def load_profile(path: Path) -> Profile:
    return Profile.model_validate(yaml.safe_load(path.read_text()))


def profile_from_data(data: dict[str, Any]) -> Profile:
    return Profile.model_validate(data)
