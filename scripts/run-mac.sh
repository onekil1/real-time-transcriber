#!/usr/bin/env bash
# Транскрибатор — быстрый запуск на macOS.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -x /usr/local/bin/brew ]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi
export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
  echo "[ОШИБКА] uv не найден. Сначала выполните: bash scripts/install-mac.sh" >&2
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "[ОШИБКА] .venv не найден. Сначала выполните: bash scripts/install-mac.sh" >&2
  exit 1
fi

if ! curl -fsS --max-time 2 http://127.0.0.1:1234/v1/models >/dev/null 2>&1; then
  echo "[WARN] LM Studio не отвечает на http://127.0.0.1:1234 — отчёты работать не будут."
fi

PORT="${MEETING_SCRIBE_PORT:-8765}"
URL="http://127.0.0.1:${PORT}"
echo "Запускаем Транскрибатор → ${URL}"
(sleep 2 && open "${URL}") &

exec uv run python run.py
