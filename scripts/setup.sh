#!/usr/bin/env bash
# One-time environment setup for voc-analyzer.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Syncing dependencies (with dev extras)"
uv sync --extra dev

echo "==> Installing Chromium for Playwright"
uv run playwright install chromium

if [ ! -f .env ]; then
  echo "==> Creating .env from template"
  cp .env.example .env
fi

echo "==> Done. Try: uv run voc-analyzer run -p 'Acme Buds' --from-raw data/samples/comments.jsonl"
