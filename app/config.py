from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "MeetingScribe"


def _default_data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


DATA_DIR = Path(os.environ.get("MEETING_SCRIBE_DATA", str(_default_data_dir())))
AUDIO_DIR = DATA_DIR / "audio"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
REPORT_DIR = DATA_DIR / "reports"
DB_PATH = DATA_DIR / "db.sqlite3"

HOST = os.environ.get("MEETING_SCRIBE_HOST", "127.0.0.1")
PORT = int(os.environ.get("MEETING_SCRIBE_PORT", "8765"))
BASE_URL = f"http://{HOST}:{PORT}"

# ASR-бэкенд: mlx (Apple Silicon) или faster (Windows / CPU).
# По умолчанию — по платформе; можно переопределить env-переменной.
ASR_BACKEND = os.environ.get(
    "MEETING_SCRIBE_ASR_BACKEND",
    "mlx" if sys.platform == "darwin" else "faster",
).lower()

# Устройство для faster-whisper: cuda (RTX), cpu.
ASR_DEVICE = os.environ.get(
    "MEETING_SCRIBE_ASR_DEVICE",
    "cuda" if ASR_BACKEND == "faster" else "auto",
).lower()

# Тип вычислений для faster-whisper (float16 на GPU, int8 на CPU экономит память).
ASR_COMPUTE_TYPE = os.environ.get(
    "MEETING_SCRIBE_ASR_COMPUTE",
    "float16" if ASR_DEVICE == "cuda" else "int8",
)

# HF-repo по умолчанию — разный для бэкендов.
_DEFAULT_WHISPER_HF = (
    "mlx-community/whisper-large-v3-mlx"
    if ASR_BACKEND == "mlx"
    else "Systran/faster-whisper-large-v3"
)
WHISPER_MODEL = os.environ.get("MEETING_SCRIBE_WHISPER", _DEFAULT_WHISPER_HF)

# LLM через LM Studio (OpenAI-совместимый API)
LM_STUDIO_BASE_URL = os.environ.get(
    "MEETING_SCRIBE_LMSTUDIO_URL", "http://127.0.0.1:1234/v1"
)
LM_STUDIO_MODEL = os.environ.get(
    "MEETING_SCRIBE_LMSTUDIO_MODEL", ""  # пустая строка = «первая доступная модель»
)
LM_STUDIO_API_KEY = os.environ.get("MEETING_SCRIBE_LMSTUDIO_KEY", "lm-studio")
LLM_MAX_TOKENS = int(os.environ.get("MEETING_SCRIBE_LLM_MAX_TOKENS", "2048"))
LLM_TEMPERATURE = float(os.environ.get("MEETING_SCRIBE_LLM_TEMPERATURE", "0.2"))
LLM_CHUNK_CHARS = int(os.environ.get("MEETING_SCRIBE_LLM_CHUNK_CHARS", "8000"))

SAMPLE_RATE = 48000
CHANNELS = 1

# ffmpeg-препроцессинг перед Whisper: highpass + spectral denoise + нормализация.
# Заодно ресемплинг в 16 kHz mono — Whisper всё равно ресемплит внутри.
DENOISE = os.environ.get("MEETING_SCRIBE_DENOISE", "1").lower() not in ("0", "false", "no", "")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
MODELS_DIR = PROJECT_ROOT / "models"

# Для каждого бэкенда своя подпапка (разные форматы файлов модели).
#   models/whisper/mac/ — MLX (*.safetensors / *.npz)
#   models/whisper/win/ — CTranslate2 (model.bin, config.json, tokenizer.json, vocabulary.txt)
# Fallback на models/whisper/ для обратной совместимости со старыми установками.
_WHISPER_SUBDIR = "mac" if ASR_BACKEND == "mlx" else "win"
LOCAL_WHISPER_DIR = MODELS_DIR / "whisper" / _WHISPER_SUBDIR
_LEGACY_WHISPER_DIR = MODELS_DIR / "whisper"


def _mlx_model_ready(d: Path) -> bool:
    return d.exists() and (any(d.glob("*.safetensors")) or any(d.glob("*.npz")))


def _ct2_model_ready(d: Path) -> bool:
    return d.exists() and (d / "model.bin").exists()


def _local_whisper_ready(d: Path) -> bool:
    if ASR_BACKEND == "mlx":
        return _mlx_model_ready(d)
    return _ct2_model_ready(d)


def whisper_model_ref() -> str:
    """Если в models/whisper/<platform>/ лежит локальная модель — берём её, иначе HF-repo id."""
    if _local_whisper_ready(LOCAL_WHISPER_DIR):
        return str(LOCAL_WHISPER_DIR)
    if _local_whisper_ready(_LEGACY_WHISPER_DIR):
        return str(_LEGACY_WHISPER_DIR)
    return WHISPER_MODEL


def ensure_local_whisper(progress_cb=None) -> Path:
    """Гарантирует, что модель Whisper лежит в models/whisper/<platform>/.

    Если её там нет — материализует через snapshot_download прямо в
    LOCAL_WHISPER_DIR. Если модель уже скачана в HF-кэш (~/.cache/huggingface),
    snapshot_download просто скопирует файлы оттуда без сетевой нагрузки;
    если её нет — скачает.
    """
    if _local_whisper_ready(LOCAL_WHISPER_DIR):
        return LOCAL_WHISPER_DIR
    if _local_whisper_ready(_LEGACY_WHISPER_DIR):
        return _LEGACY_WHISPER_DIR

    LOCAL_WHISPER_DIR.mkdir(parents=True, exist_ok=True)
    from huggingface_hub import snapshot_download

    if progress_cb:
        progress_cb(f"Материализую модель {WHISPER_MODEL} → {LOCAL_WHISPER_DIR} ...")
    # local_dir_use_symlinks выпилен в huggingface_hub 1.0+, поэтому не передаём его.
    snapshot_download(
        repo_id=WHISPER_MODEL,
        local_dir=str(LOCAL_WHISPER_DIR),
    )
    if not _local_whisper_ready(LOCAL_WHISPER_DIR):
        raise RuntimeError(
            f"snapshot_download отработал, но в {LOCAL_WHISPER_DIR} нет ожидаемых "
            "файлов модели. Проверьте права и содержимое папки."
        )
    return LOCAL_WHISPER_DIR


def whisper_is_local() -> bool:
    return _local_whisper_ready(LOCAL_WHISPER_DIR) or _local_whisper_ready(_LEGACY_WHISPER_DIR)


def ensure_dirs() -> None:
    for p in (DATA_DIR, AUDIO_DIR, TRANSCRIPT_DIR, REPORT_DIR):
        p.mkdir(parents=True, exist_ok=True)
