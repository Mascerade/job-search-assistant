"""Configuration from environment variables.

Locally these come from `pipeline/.env` (gitignored); in GitHub Actions they come
from repository secrets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PIPELINE_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = PIPELINE_DIR.parent

load_dotenv(PIPELINE_DIR / ".env")


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    supabase_url: str
    supabase_secret_key: str


def load_config() -> Config:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    missing = [name for name, val in (("SUPABASE_URL", url), ("SUPABASE_SECRET_KEY", key)) if not val]
    if missing:
        raise ConfigError(
            f"Missing {', '.join(missing)}. Copy pipeline/.env.example to pipeline/.env and fill it in."
        )
    return Config(supabase_url=url, supabase_secret_key=key)  # type: ignore[arg-type]
