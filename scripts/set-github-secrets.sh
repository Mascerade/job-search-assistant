#!/usr/bin/env bash
# Copies SUPABASE_URL and SUPABASE_SECRET_KEY from pipeline/.env.production into this
# repo's GitHub Actions secrets. Values are piped straight to `gh`; nothing is printed.
set -euo pipefail
cd "$(dirname "$0")/.."
env_file=pipeline/.env.production
[ -f "$env_file" ] || { echo "Missing $env_file — fill it in first." >&2; exit 1; }
for name in SUPABASE_URL SUPABASE_SECRET_KEY; do
  value=$(grep -E "^${name}=" "$env_file" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
  [ -n "$value" ] || { echo "$name is empty in $env_file" >&2; exit 1; }
  printf '%s' "$value" | gh secret set "$name"
  echo "✓ set $name"
done
