#!/usr/bin/env bash
# Транскрибатор (real-time) — установщик для macOS (Apple Silicon).
# Для Windows используйте scripts/install.bat.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=========================================================="
echo "  Транскрибатор (real-time) — установка для macOS"
echo "=========================================================="
echo

# --- 1. Homebrew ----------------------------------------------------
echo "[1/7] Проверяем Homebrew..."
if ! command -v brew >/dev/null 2>&1; then
  echo "    Homebrew не найден. Устанавливаем..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Добавить brew в PATH для текущей сессии (Apple Silicon / Intel)
  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
  if ! command -v brew >/dev/null 2>&1; then
    echo "    [ОШИБКА] Homebrew не установился. Поставьте вручную с https://brew.sh и повторите запуск." >&2
    exit 1
  fi
fi
echo "    OK"

# --- 2. ffmpeg ------------------------------------------------------
echo "[2/7] Проверяем ffmpeg..."
if ! command -v ffmpeg >/dev/null 2>&1; then
  brew install ffmpeg
else
  echo "    OK"
fi

# --- 3. uv ----------------------------------------------------------
echo "[3/7] Проверяем uv..."
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
else
  echo "    OK"
fi

# --- 4. venv + зависимости -----------------------------------------
echo "[4/7] Создаём venv и ставим зависимости..."
if [ ! -d ".venv" ]; then
  uv venv --python 3.11
else
  echo "    .venv уже существует — пропускаем создание."
fi
uv pip install --python .venv/bin/python -e .

# --- 5. Whisper-модель ---------------------------------------------
echo "[5/7] Проверяем Whisper-модель..."
if ls models/whisper/mac/*.safetensors >/dev/null 2>&1 || ls models/whisper/mac/*.npz >/dev/null 2>&1; then
  echo "    OK: models/whisper/mac/"
elif ls models/whisper/*.safetensors >/dev/null 2>&1 || ls models/whisper/*.npz >/dev/null 2>&1; then
  echo "    OK: models/whisper/ (legacy location)"
else
  echo "[WARN] Модель Whisper (MLX) не найдена в models/whisper/mac/."
  echo "       Положите .safetensors/.npz файлы туда."
  echo "       Пример: https://huggingface.co/mlx-community/whisper-large-v3-mlx"
fi

# --- 6. LM Studio --------------------------------------------------
echo "[6/7] Проверяем LM Studio (http://127.0.0.1:1234/v1)..."
if curl -fsS --max-time 3 http://127.0.0.1:1234/v1/models >/dev/null 2>&1; then
  echo "    OK: LM Studio отвечает"
else
  echo "[WARN] LM Studio не отвечает. Установите её с https://lmstudio.ai,"
  echo "       загрузите модель и запустите локальный сервер на порту 1234."
fi

# --- 7. Ярлык на рабочем столе (автообновление из GitHub) ---------
echo "[7/7] Создаём ярлык Транскрибатор.command на рабочем столе..."
PROJECT_ABS="$(pwd -P)"
SHORTCUT="$HOME/Desktop/Транскрибатор.command"
cat > "$SHORTCUT" <<EOF
#!/usr/bin/env bash
cd "$PROJECT_ABS"
exec bash scripts/launch-mac.sh
EOF
chmod +x "$SHORTCUT"
echo "    Ярлык: $SHORTCUT"

echo
echo "=========================================================="
echo "  Готово!"
echo "=========================================================="
echo "  Запуск:   двойной клик по Транскрибатор.command на рабочем столе"
echo "            (ярлык при каждом запуске подтянет обновления из GitHub)"
echo "  Без обновления (для разработки): uv run python run.py"
echo "  Веб-UI:   http://127.0.0.1:8765"
echo "  Напоминание: при первом запуске macOS запросит доступ к микрофону."
echo "=========================================================="
