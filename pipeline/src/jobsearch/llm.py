"""Claude via the local Claude Code CLI, in headless mode (`claude -p`).

The AI steps run on Kojo's Mac and use the Claude Code login (a Harvard Claude
Enterprise seat), so they cost nothing extra. Each call is stripped down to a
plain model call: no tools, MCP servers, plugins, skills, or project files, and
our own system prompt instead of Claude Code's default one. The answer comes
back as JSON validated against a schema (`--json-schema`).

Auth: the interactive login in the macOS Keychain, or a one-year token from
`claude setup-token` in CLAUDE_CODE_OAUTH_TOKEN (better for the scheduled job).
ANTHROPIC_API_KEY is removed from the environment so it can't silently take over.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

DEFAULT_TIMEOUT_S = 600


class LLMError(RuntimeError):
    """The model call failed (bad output, CLI error, or timeout)."""


class AuthExpiredError(LLMError):
    """Claude Code isn't signed in anymore. Run `claude` and /login, or refresh the token."""


class _CliResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    is_error: bool = False
    subtype: str = ""
    result: str | None = None
    structured_output: Any = None
    total_cost_usd: float = 0.0
    duration_ms: int = 0
    api_error_status: int | str | None = None
    credential_expires_at: str | int | float | None = None
    usage: dict[str, Any] = {}
    modelUsage: dict[str, dict[str, Any]] = {}  # noqa: N815 (CLI field name)


@dataclass(frozen=True)
class LLMResponse:
    data: Any  # the structured output; callers validate it into their own models
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float  # Claude Code's estimate of the API-price equivalent (not billed)
    duration_ms: int
    credential_expires_at: datetime | None


def _expiry(raw: str | int | float | None) -> datetime | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, int | float):
        return datetime.fromtimestamp(raw / 1000 if raw > 1e12 else raw, tz=UTC)
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def claude_binary() -> str:
    path = os.environ.get("CLAUDE_BIN") or shutil.which("claude")
    if not path:
        raise LLMError("Claude Code CLI not found. Install it or set CLAUDE_BIN to its path.")
    return path


class ClaudeCode:
    """Runs one structured model call per `ask()`."""

    def __init__(
        self, *, model: str = "haiku", effort: str = "low", timeout_s: int = DEFAULT_TIMEOUT_S
    ) -> None:
        self.model = model
        self.effort = effort
        self.timeout_s = timeout_s

    def command(self, system_prompt: str, schema: dict[str, Any]) -> list[str]:
        return [
            claude_binary(),
            "-p",
            "--output-format", "json",
            "--model", self.model,
            "--effort", self.effort,
            "--tools", "",
            "--setting-sources", "",
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--no-session-persistence",
            "--system-prompt", system_prompt,
            "--json-schema", json.dumps(schema),
        ]  # fmt: skip

    def ask(self, system_prompt: str, prompt: str, schema: dict[str, Any]) -> LLMResponse:
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        # An empty working directory, so no project CLAUDE.md or settings are picked up.
        with tempfile.TemporaryDirectory(prefix="jobsearch-llm-") as cwd:
            try:
                proc = subprocess.run(
                    self.command(system_prompt, schema),
                    input=prompt,
                    capture_output=True,
                    text=True,
                    cwd=cwd,
                    env=env,
                    timeout=self.timeout_s,
                    check=False,
                )
            except subprocess.TimeoutExpired as e:
                raise LLMError(f"Claude Code timed out after {self.timeout_s}s") from e
        return self._parse(proc)

    def _parse(self, proc: subprocess.CompletedProcess[str]) -> LLMResponse:
        text = proc.stdout.strip()
        try:
            res = _CliResult.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError) as e:
            detail = (proc.stderr or text)[-500:]
            if _looks_like_auth_error(detail):
                raise AuthExpiredError(detail) from e
            raise LLMError(f"Claude Code returned non-JSON output (exit {proc.returncode}): {detail}") from e
        if res.is_error or res.structured_output is None:
            detail = f"{res.subtype}: {res.result or ''} (api status {res.api_error_status})"
            if _looks_like_auth_error(detail) or res.api_error_status in (401, "401"):
                raise AuthExpiredError(detail)
            raise LLMError(f"Claude Code call failed: {detail}"[:500])
        model = next(iter(res.modelUsage), self.model)
        usage = res.usage
        input_tokens = sum(
            int(usage.get(k) or 0)
            for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
        )
        return LLMResponse(
            data=res.structured_output,
            model=model,
            input_tokens=input_tokens,
            output_tokens=int(usage.get("output_tokens") or 0),
            cost_usd=res.total_cost_usd,
            duration_ms=res.duration_ms,
            credential_expires_at=_expiry(res.credential_expires_at),
        )  # fmt: skip


def _looks_like_auth_error(text: str) -> bool:
    t = text.lower()
    return any(s in t for s in ("login expired", "/login", "oauth", "authentication_failed", "not logged in"))
