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

# JOBSEARCH_ENV=production loads pipeline/.env.production (your hosted Supabase) instead
# of pipeline/.env (local). In GitHub Actions neither file exists; secrets come from the
# environment, and load_dotenv never overrides variables that are already set.
ENV_NAME = os.environ.get("JOBSEARCH_ENV", "").strip()
ENV_FILE = PIPELINE_DIR / (f".env.{ENV_NAME}" if ENV_NAME else ".env")
load_dotenv(ENV_FILE)


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
    if not url or not key:
        raise ConfigError(
            f"Missing {', '.join(missing)} (looked in {ENV_FILE.name}). "
            "Copy pipeline/.env.example to that file and fill it in."
        )
    return Config(supabase_url=url, supabase_secret_key=key)
