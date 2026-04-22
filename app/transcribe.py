from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

import soundfile as sf

from .config import (
    ASR_BACKEND,
    ASR_COMPUTE_TYPE,
    ASR_DEVICE,
    LOCAL_WHISPER_DIR,
    SAMPLE_RATE,
    WHISPER_MODEL,
    whisper_is_local,
    whisper_model_ref,
)

AUDIO_EXT_OK = {".wav"}
AUDIO_EXT_CONVERT = {".mp3", ".m4a", ".mp4", ".mov", ".aac", ".flac", ".ogg", ".webm"}

_HALLUCINATION_MARKERS = (
    "субтитры",
    "dimatorzok",
    "продолжение следует",
    "спасибо за просмотр",
    "подпишитесь на канал",
    "ставьте лайк",
    "редактор субтитров",
    "корректор субтитров",
    "субтитры делал",
    "игорь жадан",
)


def _is_hallucination(text: str) -> bool:
    t = text.lower()
    return any(m in t for m in _HALLUCINATION_MARKERS)


_RU_ANCHOR_PROMPT = (
    "Стенограмма рабочего совещания на русском языке. "
    "Обсуждаются задачи, сроки, решения и вопросы участников."
)


def _build_initial_prompt(glossary: str | None) -> str:
    """Склеить якорь с пользовательским глоссарием (имена, термины, аббревиатуры).

    Whisper использует initial_prompt как подсказку по написанию слов — перечисление
    имён и специфичных терминов резко снижает ошибки на собственных именах и жаргоне.
    """
    g = (glossary or "").strip()
    if not g:
        return _RU_ANCHOR_PROMPT
    return f"{_RU_ANCHOR_PROMPT} Участники и термины: {g}"


def _have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def model_info() -> dict[str, Any]:
    """Информация о модели Whisper."""
    ref = whisper_model_ref()
    local = whisper_is_local()
    info: dict[str, Any] = {
        "ok": True,
        "backend": ASR_BACKEND,
        "device": ASR_DEVICE,
        "compute_type": ASR_COMPUTE_TYPE,
        "ref": ref,
        "source": "local" if local else "hf",
        "hf_repo": WHISPER_MODEL,
        "local_dir": str(LOCAL_WHISPER_DIR),
        "ffmpeg": _have_ffmpeg(),
    }
    if local:
        d = Path(ref)
        if d.is_dir():
            info["files"] = sorted(
                p.name for p in d.iterdir() if p.is_file()
            )
    else:
        info["hint"] = (
            "Локальной модели нет — будет скачана с HuggingFace при первом запуске."
        )
    return info


def ensure_wav(src: Path) -> Path:
    """Вернуть путь к WAV. Если нужно — конвертировать через ffmpeg."""
    src = Path(src)
    if src.suffix.lower() in AUDIO_EXT_OK:
        return src
    if not _have_ffmpeg():
        raise RuntimeError(
            "Для нестандартных форматов нужен ffmpeg (brew install ffmpeg / winget install Gyan.FFmpeg)"
        )
    tmp = Path(tempfile.mkdtemp(prefix="scribe_")) / (src.stem + ".wav")
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "wav", str(tmp),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return tmp


def _filter_segments(raw_segments) -> list[dict[str, Any]]:
    raw_list = list(raw_segments)
    # ВРЕМЕННАЯ ДИАГНОСТИКА: показать сырой выход модели до фильтрации.
    import sys
    raw_texts = [str(s.get("text", "")).strip() for s in raw_list]
    print(
        f"[ASR raw] segments={len(raw_list)} texts={raw_texts!r}",
        file=sys.stderr, flush=True,
    )
    out: list[dict[str, Any]] = []
    dropped_halluc = 0
    dropped_empty = 0
    dropped_dup = 0
    last_text = ""
    for s in raw_list:
        text = str(s.get("text", "")).strip()
        if not text:
            dropped_empty += 1
            continue
        if _is_hallucination(text):
            dropped_halluc += 1
            continue
        if text == last_text:
            dropped_dup += 1
            continue
        out.append({
            "start": float(s.get("start", 0.0)),
            "end": float(s.get("end", 0.0)),
            "text": text,
        })
        last_text = text
    print(
        f"[ASR filt] kept={len(out)} empty={dropped_empty} "
        f"halluc={dropped_halluc} dup={dropped_dup}",
        file=sys.stderr, flush=True,
    )
    return out


_ASR_TEMPERATURES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


# ---------- Silero VAD (macOS) -----------------------------------------------

_vad_model = None
_vad_lock = threading.Lock()
_vad_import_failed = False


def _load_silero_vad():
    """Лениво загрузить Silero VAD. Вернуть None, если пакет не установлен."""
    global _vad_model, _vad_import_failed
    if _vad_import_failed:
        return None
    if _vad_model is not None:
        return _vad_model
    with _vad_lock:
        if _vad_model is None and not _vad_import_failed:
            try:
                from silero_vad import load_silero_vad
                _vad_model = load_silero_vad()
            except Exception:
                _vad_import_failed = True
                return None
    return _vad_model


def _silero_extract_speech(
    wav_path: Path,
) -> tuple[str, Path | None, list[tuple[float, float]] | None]:
    """Прогнать WAV через Silero VAD.

    Возврат:
      ("skip", None, None)   — VAD недоступен, обрабатывать аудио как есть.
      ("empty", None, None)  — VAD запустился, речи не найдено — пустой транскрипт.
      ("ok", speech_wav, offsets) — склейка речи + таблица смещений [(cum_sec, orig_sec)].
    """
    model = _load_silero_vad()
    if model is None:
        return ("skip", None, None)
    try:
        import torch  # noqa: F401 (silero тянет torch как транзитив)
        from silero_vad import get_speech_timestamps, read_audio

        wav = read_audio(str(wav_path), sampling_rate=16000)
        ts = get_speech_timestamps(
            wav,
            model,
            sampling_rate=16000,
            min_silence_duration_ms=500,
        )
        if not ts:
            return ("empty", None, None)

        import torch as _t

        pieces = [wav[t["start"]:t["end"]] for t in ts]
        offsets: list[tuple[float, float]] = []
        cum_samples = 0
        for t, piece in zip(ts, pieces):
            offsets.append((cum_samples / 16000.0, t["start"] / 16000.0))
            cum_samples += piece.shape[0]
        concat = _t.cat(pieces)

        tmp_dir = Path(tempfile.mkdtemp(prefix="vad_"))
        tmp = tmp_dir / "speech.wav"
        sf.write(str(tmp), concat.numpy(), 16000)
        return ("ok", tmp, offsets)
    except Exception:
        return ("skip", None, None)


def _remap_time(t: float, offsets: list[tuple[float, float]]) -> float:
    """Перевести время в склейке обратно во время в исходном аудио."""
    orig = t
    for cum, orig_off in offsets:
        if cum <= t:
            orig = t - cum + orig_off
        else:
            break
    return orig


# ---------- MLX backend (macOS Apple Silicon) --------------------------------

def _mlx_transcribe(
    wav_path: Path, language: str | None, glossary: str | None = None
) -> dict[str, Any]:
    import mlx_whisper

    status, speech_wav, offsets = _silero_extract_speech(wav_path)
    if status == "empty":
        return {"text": "", "segments": [], "language": language}
    source = speech_wav if status == "ok" else wav_path

    result = mlx_whisper.transcribe(
        str(source),
        path_or_hf_repo=whisper_model_ref(),
        language=language,
        task="transcribe",
        word_timestamps=False,
        initial_prompt=_build_initial_prompt(glossary),
        condition_on_previous_text=False,
        temperature=_ASR_TEMPERATURES,
        verbose=False,
    )
    segments = result.get("segments", []) or []
    if status == "ok" and offsets:
        for s in segments:
            s["start"] = _remap_time(float(s.get("start", 0.0)), offsets)
            s["end"] = _remap_time(float(s.get("end", 0.0)), offsets)
    return {
        "text": (result.get("text") or "").strip(),
        "segments": segments,
        "language": result.get("language", language),
    }


# ---------- faster-whisper backend (Windows / CPU) ---------------------------

_faster_model = None
_faster_lock = threading.Lock()


def _faster_get_model():
    global _faster_model
    if _faster_model is not None:
        return _faster_model
    with _faster_lock:
        if _faster_model is None:
            from faster_whisper import WhisperModel

            _faster_model = WhisperModel(
                whisper_model_ref(),
                device=ASR_DEVICE,
                compute_type=ASR_COMPUTE_TYPE,
            )
    return _faster_model


def _faster_transcribe(
    wav_path: Path, language: str | None, glossary: str | None = None
) -> dict[str, Any]:
    model = _faster_get_model()
    segments_iter, info = model.transcribe(
        str(wav_path),
        language=language,
        task="transcribe",
        initial_prompt=_build_initial_prompt(glossary),
        condition_on_previous_text=False,
        word_timestamps=False,
        beam_size=5,
        temperature=_ASR_TEMPERATURES,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        hotwords=(glossary or None),
    )
    segs = [
        {"start": float(s.start), "end": float(s.end), "text": (s.text or "").strip()}
        for s in segments_iter
    ]
    text = " ".join(s["text"] for s in segs).strip()
    return {"text": text, "segments": segs, "language": info.language or language}


# ---------- единый интерфейс -------------------------------------------------

def _backend_transcribe(
    wav_path: Path, language: str | None, glossary: str | None = None
) -> dict[str, Any]:
    if ASR_BACKEND == "mlx":
        return _mlx_transcribe(wav_path, language, glossary)
    return _faster_transcribe(wav_path, language, glossary)


def transcribe_chunk(
    wav_path: Path,
    prior_text: str = "",  # не используется — оставлен для совместимости
    language: str | None = "ru",
    glossary: str | None = None,
) -> list[dict[str, Any]]:
    """Транскрибация одного чанка."""
    result = _backend_transcribe(Path(wav_path), language, glossary)
    return _filter_segments(result["segments"])


def transcribe_file(
    path: Path,
    language: str | None = "ru",
    progress_cb=None,
    glossary: str | None = None,
) -> dict[str, Any]:
    """Полная транскрибация файла. Возвращает dict с text + segments."""
    wav = ensure_wav(Path(path))

    if progress_cb:
        progress_cb("asr:model_load", 0.0)

    result = _backend_transcribe(wav, language, glossary)

    if progress_cb:
        progress_cb("asr:done", 1.0)

    return {
        "text": result["text"],
        "segments": _filter_segments(result["segments"]),
        "language": result.get("language", language),
    }
