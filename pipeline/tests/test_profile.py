from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from jobsearch.profile import Profile, load_profile

FIXTURE = Path(__file__).parent / "fixtures" / "profile_example.yaml"


def example() -> dict:
    return yaml.safe_load(FIXTURE.read_text())


def test_example_profile_is_valid():
    profile = load_profile(FIXTURE)
    assert set(profile.fact_index()) == {"acme-api", "weather-bot"}
    assert "python" in profile.all_skills()


def test_placeholder_is_rejected():
    data = example()
    data["experience"][0]["facts"][0]["text"] = "Cut review time [by X%]."
    with pytest.raises(ValidationError, match="placeholder"):
        Profile.model_validate(data)


def test_duplicate_fact_ids_are_rejected():
    data = example()
    data["projects"][0]["facts"][0]["id"] = "acme-api"
    with pytest.raises(ValidationError, match="duplicate fact id"):
        Profile.model_validate(data)


def test_unknown_keys_are_rejected():
    data = example()
    data["contact"]["nickname"] = "Al"
    with pytest.raises(ValidationError):
        Profile.model_validate(data)


def test_fact_ids_must_be_slugs():
    data = example()
    data["experience"][0]["facts"][0]["id"] = "Acme API"
    with pytest.raises(ValidationError):
        Profile.model_validate(data)


def test_extra_facts_count_as_facts():
    data = example()
    data["extra_facts"] = [{"id": "volunteer-tutor", "text": "Tutored middle schoolers in math."}]
    assert "volunteer-tutor" in Profile.model_validate(data).fact_index()
