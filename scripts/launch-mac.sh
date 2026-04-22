#!/usr/bin/env bash
# Транскрибатор — запуск с авто-обновлением из GitHub (macOS).
# При каждом старте: git pull -> uv pip install -> run.py.
# Если интернета нет или pull упал — запускаем текущую локальную версию.

set -u  # без -e, чтобы апдейт не валил запуск

cd "$(dirname "$0")/.."

# PATH для brew/uv в not-login shell (двойной клик по .command)
if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -x /usr/local/bin/brew ]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi
export PATH="$HOME/.local/bin:$PATH"

echo "=== Проверяем обновления ==="
if ! command -v git >/dev/null 2>&1; then
  echo "[WARN] git не найден — автообновление пропущено."
elif [ ! -d .git ]; then
  echo "[WARN] не git-репозиторий — автообновление пропущено."
else
  if git pull --ff-only --quiet; then
    echo "    OK: код актуален."
  else
    echo "[WARN] git pull не удался — запускаем текущую версию."
  fi
fi

echo "=== Синхронизируем зависимости ==="
if ! command -v uv >/dev/null 2>&1; then
  echo "[WARN] uv не найден — пропускаем sync. Запустите bash scripts/install-mac.sh."
elif [ -d .venv ]; then
  uv pip install --quiet --python .venv/bin/python -e . \
    || echo "[WARN] Не удалось синхронизировать зависимости."
fi

if [ ! -x .venv/bin/python ]; then
  echo "[ОШИБКА] .venv не найден. Запустите: bash scripts/install-mac.sh" >&2
  read -r -p "Enter для выхода..." _
  exit 1
fi

PORT="${MEETING_SCRIBE_PORT:-8765}"
URL="http://127.0.0.1:${PORT}"
echo "=== Запуск → ${URL} ==="
(sleep 2 && open "${URL}") &

exec .venv/bin/python run.py
