"""The master profile: the only source of facts the tailoring step may use.

Every resume bullet the AI writes must cite the `id` of the fact(s) it came from.
Anything it can't cite becomes a *suggestion* that Kojo approves or rejects.

The website's validator (web/src/lib/profile.ts) mirrors these rules.
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


def load_profile(path: Path) -> Profile:
    return Profile.model_validate(yaml.safe_load(path.read_text()))


def profile_from_data(data: dict[str, Any]) -> Profile:
    return Profile.model_validate(data)
