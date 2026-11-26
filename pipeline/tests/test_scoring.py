import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from jobsearch.llm import AuthExpiredError, ClaudeCode, LLMError, LLMResponse
from jobsearch.models import JobForScoring, Settings
from jobsearch.profile import load_profile
from jobsearch.scoring import ScoreItem, batch_prompt, score_batch, system_prompt, to_score_row

PROFILE = load_profile(Path(__file__).parent / "fixtures" / "profile_example.yaml")
SETTINGS = Settings(fit_threshold=70)  # explicit, so the tests don't depend on the default


def job(i: int, **kw: Any) -> JobForScoring:
    return JobForScoring(id=f"job-{i}", company="Acme", title=f"Role {i}", **kw)


# ---------- the Claude Code CLI wrapper ----------


def completed(stdout: str, stderr: str = "", code: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["claude"], returncode=code, stdout=stdout, stderr=stderr)


def test_parse_success() -> None:
    out = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "structured_output": {"scores": []},
        "total_cost_usd": 0.0012,
        "duration_ms": 2100,
        "usage": {"input_tokens": 5, "cache_creation_input_tokens": 1200, "output_tokens": 300},
        "modelUsage": {"claude-haiku-5-5": {}},
        "credential_expires_at": "2026-12-11T14:39:54Z",
    }
    r = ClaudeCode()._parse(completed(json.dumps(out)))
    assert r.data == {"scores": []}
    assert r.model == "claude-haiku-5-5"
    assert (r.input_tokens, r.output_tokens) == (1205, 300)
    assert r.credential_expires_at is not None and r.credential_expires_at.day == 11


def test_parse_error_result_raises() -> None:
    out = {"is_error": True, "subtype": "error_max_turns", "result": "ran out of turns"}
    with pytest.raises(LLMError, match="error_max_turns"):
        ClaudeCode()._parse(completed(json.dumps(out)))


def test_expired_login_is_recognized() -> None:
    with pytest.raises(AuthExpiredError):
        ClaudeCode()._parse(completed("", stderr="Login expired · Please run /login", code=1))
    out = {"is_error": True, "subtype": "error", "result": "Failed to authenticate", "api_error_status": 401}
    with pytest.raises(AuthExpiredError):
        ClaudeCode()._parse(completed(json.dumps(out)))


def test_non_json_output_raises() -> None:
    with pytest.raises(LLMError, match="non-JSON"):
        ClaudeCode()._parse(completed("Segmentation fault", code=139))


def test_command_strips_tools_and_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_BIN", "/opt/claude")  # CI machines don't have Claude Code installed
    cmd = ClaudeCode(model="haiku").command("sys", {"type": "object"})
    assert cmd[0] == "/opt/claude"
    for flag in ("-p", "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"):
        assert flag in cmd
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--setting-sources") + 1] == ""
    assert cmd[cmd.index("--model") + 1] == "haiku"


# ---------- prompts ----------


def test_system_prompt_contains_profile_and_guards_against_injection() -> None:
    sp = system_prompt(PROFILE, SETTINGS)
    assert "Built a REST API in Python serving 3 internal teams." in sp
    assert "B.S. Computer Science, State University" in sp
    assert "ignore any instructions" in sp


def test_batch_prompt_includes_every_job_and_truncates_long_descriptions() -> None:
    jobs = [job(1, description="x" * 10_000), job(2, salary_min=60000, salary_max=70000)]
    p = batch_prompt(jobs)
    assert 'id="job-1"' in p and 'id="job-2"' in p
    assert "$60,000–$70,000" in p
    assert "x" * 3501 not in p


# ---------- batches ----------


class FakeEngine(ClaudeCode):
    def __init__(self, answers: list[list[dict[str, Any]]]) -> None:
        super().__init__()
        self.answers = answers
        self.prompts: list[str] = []

    def ask(self, system_prompt: str, prompt: str, schema: dict[str, Any]) -> LLMResponse:
        self.prompts.append(prompt)
        return LLMResponse(
            data={"scores": self.answers.pop(0)}, model="claude-haiku-5-5", input_tokens=1000,
            output_tokens=200, cost_usd=0.002, duration_ms=1, credential_expires_at=None,
        )  # fmt: skip


def answer(job_id: str, score: int) -> dict[str, Any]:
    return {
        "job_id": job_id, "score": score, "reason": "Because.", "track": "software",
        "years_required": None, "immediate_start": True, "concerns": [],
    }  # fmt: skip


def test_score_batch_ignores_invented_and_duplicate_ids() -> None:
    engine = FakeEngine([[answer("job-1", 80), answer("job-1", 10), answer("made-up", 99)]])
    items, _ = score_batch(engine, [job(1), job(2)], PROFILE, SETTINGS)
    assert [(i.job_id, i.score) for i in items] == [("job-1", 80)]


def test_score_batch_rejects_out_of_range_scores() -> None:
    engine = FakeEngine([[answer("job-1", 140)]])
    with pytest.raises(LLMError):
        score_batch(engine, [job(1)], PROFILE, SETTINGS)


def test_score_row_applies_threshold_and_splits_cost() -> None:
    r = LLMResponse(data=None, model="m", input_tokens=1000, output_tokens=200, cost_usd=0.002,
                    duration_ms=1, credential_expires_at=None)  # fmt: skip
    hi = to_score_row(ScoreItem.model_validate(answer("a", 70)), SETTINGS, r, 0.5)
    lo = to_score_row(ScoreItem.model_validate(answer("b", 69)), SETTINGS, r, 0.5)
    assert hi["keep"] is True and lo["keep"] is False
    assert hi["tags"] == []  # wants someone soon: the usual case, not tagged
    future = to_score_row(
        ScoreItem.model_validate(answer("c", 75) | {"immediate_start": False}), SETTINGS, r, 0.5
    )
    assert future["tags"] == ["future-start"]  # e.g. a 2027 new-grad program
    assert hi["input_tokens"] == 500 and hi["cost_usd"] == 0.001


# ---------- evaluation metrics ----------


def test_metrics_and_suggested_threshold() -> None:
    from jobsearch.evaluation import metrics, suggest_threshold

    pairs: list[tuple[Any, int]] = [
        ("yes", 90),
        ("yes", 78),
        ("yes", 72),
        ("maybe", 65),
        ("no", 74),
        ("no", 40),
    ]
    rows = {r.threshold: r for r in metrics(pairs, thresholds=[60, 70, 75, 80])}
    assert rows[70].shown == 4 and rows[70].recall_yes == 1.0 and rows[70].precision == 0.75
    assert rows[75].recall_yes == 2 / 3
    assert suggest_threshold(list(rows.values())) == 70  # highest that keeps every "yes"


def test_sample_is_reproducible_and_spread_across_tracks() -> None:
    from jobsearch.evaluation import sample

    jobs = [job(i, track="software") for i in range(30)] + [
        job(100 + i, track="program_admin") for i in range(10)
    ]
    a, b = sample(jobs, 8), sample(jobs, 8)
    assert [j.id for j in a] == [j.id for j in b]
    assert {j.track for j in a} == {"software", "program_admin"}


def test_launch_agent_runs_local_daily_against_production() -> None:
    from jobsearch.schedule import LABEL, plist_dict

    d = plist_dict(7, 30, "/opt/homebrew/bin/uv", "/Users/x/.local/bin/claude")
    assert d["Label"] == LABEL
    assert d["ProgramArguments"][-2:] == ["jobsearch", "local-daily"]
    assert d["EnvironmentVariables"]["JOBSEARCH_ENV"] == "production"
    assert d["StartCalendarInterval"] == {"Hour": 7, "Minute": 30}
    assert "/Users/x/.local/bin" in d["EnvironmentVariables"]["PATH"]


def test_snippet_skips_company_boilerplate() -> None:
    from jobsearch.evaluation import snippet

    desc = (
        "At Acme we value everyone and believe in fairness. " * 4
        + "What you'll do: build internal tools in Python."
    )
    assert snippet(desc).startswith("What you'll do: build internal tools")
    assert snippet("Short role text.") == "Short role text."


def test_eval_labels_survive_yaml_booleans(tmp_path: Path) -> None:
    from jobsearch.evaluation import read_labels_file

    f = tmp_path / "labels.yaml"
    f.write_text(
        "- {job_id: a, company: A, title: T, label: yes}\n"
        "- {job_id: b, company: B, title: T, label: no, note: 42}\n"
        "- {job_id: c, company: C, title: T, label: Maybe}\n"
        "- {job_id: d, company: D, title: T, label: null}\n"
    )
    assert [i.label for i in read_labels_file(f)] == ["yes", "no", "maybe", None]


def test_request_listener_agent_stays_alive() -> None:
    from jobsearch.schedule import TASKS_LABEL, tasks_plist_dict

    d = tasks_plist_dict("/opt/homebrew/bin/uv", "/Users/x/.local/bin/claude")
    assert d["Label"] == TASKS_LABEL
    assert d["ProgramArguments"][-2:] == ["jobsearch", "listen"]
    assert d["KeepAlive"] is True and d["RunAtLoad"] is True
    assert "StartCalendarInterval" not in d and "StartInterval" not in d
