#!/usr/bin/env bash
# Copies SUPABASE_URL, SUPABASE_SECRET_KEY (and ADZUNA_APP_ID/KEY if present) from
# pipeline/.env.production into this repo's GitHub Actions secrets. Values are piped straight to `gh`; nothing is printed.
set -euo pipefail
cd "$(dirname "$0")/.."
env_file=pipeline/.env.production
[ -f "$env_file" ] || { echo "Missing $env_file — fill it in first." >&2; exit 1; }
read_value() {
  grep -E "^$1=" "$env_file" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" || true
}
for name in SUPABASE_URL SUPABASE_SECRET_KEY; do  # required
  value=$(read_value "$name")
  [ -n "$value" ] || { echo "$name is empty in $env_file" >&2; exit 1; }
  printf '%s' "$value" | gh secret set "$name"
  echo "✓ set $name"
done
for name in ADZUNA_APP_ID ADZUNA_APP_KEY; do  # optional: the Adzuna job source
  value=$(read_value "$name")
  if [ -z "$value" ]; then
    echo "- skipped $name (not in $env_file)"
    continue
  fi
  printf '%s' "$value" | gh secret set "$name"
  echo "✓ set $name"
done
