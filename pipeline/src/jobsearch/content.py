"""The structured content of a tailored resume and cover letter.

The model writes *only* this: which profile entries to include, in what order, and
the wording of bullets and letter paragraphs — each citing the fact ids it's based
on. Names, contact details, education, job titles, employers, and dates are filled
in from the master profile by the renderer, so the model can't get them wrong.

Anything the model can't ground in a fact must be marked `suggestion` with a reason;
those wait for Kojo's approval before a final PDF is made.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Template = Literal["technical", "admin"]


class Line(BaseModel):
    """A resume bullet, summary, or cover-letter paragraph."""

    text: str = Field(min_length=1, max_length=900)
    fact_ids: list[str] = Field(default_factory=list)
    suggestion: bool = False
    rationale: str | None = None  # why it's a suggestion (required when suggestion=True)


class EntryBlock(BaseModel):
    entry_id: str  # an experience or project id from the profile
    bullets: list[Line] = Field(min_length=1, max_length=6)


class SkillSuggestion(BaseModel):
    """A skill the posting wants that isn't in the profile yet."""

    skill: str
    category: str = ""  # the profile skill group it belongs in
    obvious: bool = False  # the profile makes it near-certain (e.g. SQL given PostgreSQL)
    basis: str = ""  # which profile items imply it


class SkillLine(BaseModel):
    category: str
    items: list[str] = Field(min_length=1)


class ResumeContent(BaseModel):
    template: Template
    headline: str | None = None  # admin layout: "Program operations • Event logistics • Data and systems"
    summary: Line | None = None  # technical layout: 1–2 sentences
    experience: list[EntryBlock] = Field(default_factory=list)
    projects: list[EntryBlock] = Field(default_factory=list)
    skills: list[SkillLine] = Field(default_factory=list)
    suggested_skills: list[SkillSuggestion] = Field(default_factory=list)

    @field_validator("suggested_skills", mode="before")
    @classmethod
    def _old_format(cls, v: object) -> object:
        # Version-1 documents stored plain strings.
        return [{"skill": s} if isinstance(s, str) else s for s in v] if isinstance(v, list) else v


class CoverLetterContent(BaseModel):
    greeting: str = "Dear Hiring Manager,"
    paragraphs: list[Line] = Field(min_length=2, max_length=6)
    closing: str = "Sincerely,"


class Tailored(BaseModel):
    resume: ResumeContent
    cover_letter: CoverLetterContent


def _line_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["text", "fact_ids", "suggestion", "rationale"],
        "properties": {
            "text": {"type": "string"},
            "fact_ids": {"type": "array", "items": {"type": "string"}},
            "suggestion": {"type": "boolean"},
            "rationale": {"type": ["string", "null"]},
        },
    }


def _entries_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["entry_id", "bullets"],
            "properties": {
                "entry_id": {"type": "string"},
                "bullets": {"type": "array", "items": _line_schema(), "minItems": 1, "maxItems": 6},
            },
        },
    }


# Handwritten so the model sees exactly what it must produce.
TAILOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["resume", "cover_letter"],
    "properties": {
        "resume": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "template",
                "headline",
                "summary",
                "experience",
                "projects",
                "skills",
                "suggested_skills",
            ],
            "properties": {
                "template": {"type": "string", "enum": ["technical", "admin"]},
                "headline": {"type": ["string", "null"]},
                "summary": {"anyOf": [_line_schema(), {"type": "null"}]},
                "experience": _entries_schema(),
                "projects": _entries_schema(),
                "skills": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["category", "items"],
                        "properties": {
                            "category": {"type": "string"},
                            "items": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "suggested_skills": {
                    "type": "array",
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["skill", "category", "obvious", "basis"],
                        "properties": {
                            "skill": {"type": "string"},
                            "category": {"type": "string"},
                            "obvious": {"type": "boolean"},
                            "basis": {"type": "string"},
                        },
                    },
                },
            },
        },
        "cover_letter": {
            "type": "object",
            "additionalProperties": False,
            "required": ["greeting", "paragraphs", "closing"],
            "properties": {
                "greeting": {"type": "string"},
                "paragraphs": {"type": "array", "items": _line_schema(), "minItems": 2, "maxItems": 6},
                "closing": {"type": "string"},
            },
        },
    },
}
