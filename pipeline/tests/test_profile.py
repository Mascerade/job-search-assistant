from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from jobsearch.profile import Profile, load_profile

FIXTURE = Path(__file__).parent / "fixtures" / "profile_example.yaml"


def example() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(FIXTURE.read_text())
    return data


def test_example_profile_is_valid() -> None:
    profile = load_profile(FIXTURE)
    assert set(profile.fact_index()) == {"acme-api", "weather-bot"}
    assert "python" in profile.all_skills()


def test_placeholder_is_rejected() -> None:
    data = example()
    data["experience"][0]["facts"][0]["text"] = "Cut review time [by X%]."
    with pytest.raises(ValidationError, match="placeholder"):
        Profile.model_validate(data)


def test_duplicate_fact_ids_are_rejected() -> None:
    data = example()
    data["projects"][0]["facts"][0]["id"] = "acme-api"
    with pytest.raises(ValidationError, match="duplicate fact id"):
        Profile.model_validate(data)


def test_unknown_keys_are_rejected() -> None:
    data = example()
    data["contact"]["nickname"] = "Al"
    with pytest.raises(ValidationError):
        Profile.model_validate(data)


def test_fact_ids_must_be_slugs() -> None:
    data = example()
    data["experience"][0]["facts"][0]["id"] = "Acme API"
    with pytest.raises(ValidationError):
        Profile.model_validate(data)


def test_extra_facts_count_as_facts() -> None:
    data = example()
    data["extra_facts"] = [{"id": "volunteer-tutor", "text": "Tutored middle schoolers in math."}]
    assert "volunteer-tutor" in Profile.model_validate(data).fact_index()


# ---------- application answers (apply assist) ----------


def test_application_answers_load_and_old_profiles_still_work() -> None:
    profile = load_profile(FIXTURE)
    assert profile.application is not None
    assert profile.application.work_authorized_us is True
    assert (
        profile.application.answer_for("are you open to HYBRID work")
        == "Yes, three days a week on site works for me."
    )
    data = example()
    del data["application"]
    assert Profile.model_validate(data).application is None  # profiles saved before milestone 6


def test_numeric_text_answers_from_yaml_become_text() -> None:
    data = example()
    data["application"].update({"gpa": 3.7, "salary_expectation": 85000})
    answers = Profile.model_validate(data).application
    assert answers is not None and (answers.gpa, answers.salary_expectation) == ("3.7", "85000")


def test_unknown_application_keys_are_rejected() -> None:
    data = example()
    data["application"]["work_authorised"] = True  # typo
    with pytest.raises(ValidationError):
        Profile.model_validate(data)


def test_custom_answers_keep_one_per_question() -> None:
    data = example()
    data["application"]["custom"].append({"question": "Are you open to hybrid work??", "answer": "Yes."})
    answers = Profile.model_validate(data).application
    assert answers is not None and len(answers.custom) == 1 and answers.custom[0].answer == "Yes."


def test_remember_answer_adds_and_only_replaces_when_asked() -> None:
    profile = load_profile(FIXTURE)
    assert profile.remember_answer("Do you have a driver's license?", "Yes.")
    assert not profile.remember_answer("Are you open to hybrid work?", "No.")  # different answer exists
    assert profile.remember_answer("Are you open to hybrid work?", "No.", replace=True)
    assert profile.application is not None
    assert profile.application.answer_for("Are you open to hybrid work?") == "No."
    assert len(profile.application.custom) == 2


def test_application_answers_never_reach_the_ai_prompts() -> None:
    from jobsearch.scoring import candidate_summary
    from jobsearch.tailor import profile_for_prompt

    profile = load_profile(FIXTURE)
    for prompt in (candidate_summary(profile), profile_for_prompt(profile)):
        assert "Decline to self-identify" not in prompt
        assert "hybrid work" not in prompt
        assert "sponsorship" not in prompt.lower()
