from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import soundfile as sf


def _register_cuda_dll_dirs() -> None:
    """На Windows pip-пакеты nvidia-cudnn-cu12 / nvidia-cublas-cu12 кладут DLL
    в .venv/Lib/site-packages/nvidia/<lib>/bin. ctranslate2 ищет их по системному
    PATH, поэтому до его импорта нужно явно зарегистрировать эти директории."""
    if sys.platform != "win32":
        return
    base = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    if not base.exists():
        return
    for sub in ("cudnn", "cublas", "cuda_runtime", "cuda_nvrtc"):
        bin_dir = base / sub / "bin"
        if bin_dir.exists():
            try:
                os.add_dll_directory(str(bin_dir))
            except (OSError, AttributeError):
                pass


_register_cuda_dll_dirs()

from .config import (
    ASR_BACKEND,
    ASR_COMPUTE_TYPE,
    ASR_DEVICE,
    DENOISE,
    LOCAL_WHISPER_DIR,
    SAMPLE_RATE,
    WHISPER_MODEL,
    ensure_local_whisper,
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
    "Реплики коллег с естественными повторами, паузами и междометиями. "
    "Числа писать цифрами. Английские термины и аббревиатуры оставлять латиницей "
    "(API, SLA, Kubernetes). Имена собственные — с заглавной буквы."
)

# Жёсткий лимит initial_prompt у Whisper — 224 токена (~400-600 символов
# для смешанного ru/en текста). Чтобы не схлопотать тихую обрезку, держим
# суммарный prompt в этом коридоре с запасом.
_PROMPT_BUDGET_CHARS = 500


def _build_initial_prompt(
    glossary: str | None,
    prev_context: str | None = None,
) -> str:
    """Склеить якорь + глоссарий + контекст из предыдущего чанка.

    Whisper использует initial_prompt как подсказку по написанию слов и стилю.
    Глоссарий резко снижает ошибки на именах и жаргоне; контекст из прошлого
    чанка помогает сохранить связность на стыках (имена, длинные термины,
    обсуждаемая тема).

    Бюджет суммарной длины ~500 символов — превышение Whisper тихо обрежет.
    Если не влезает — сначала режем prev_context (он наименее ценный), потом
    глоссарий с конца.
    """
    parts = [_RU_ANCHOR_PROMPT]
    g = (glossary or "").strip()
    if g:
        parts.append(f"Участники и термины: {g}")
    ctx = (prev_context or "").strip()
    if ctx and not _is_hallucination(ctx):
        parts.append(f"Контекст: …{ctx}")

    prompt = " ".join(parts)
    if len(prompt) <= _PROMPT_BUDGET_CHARS:
        return prompt

    # Урезаем сначала контекст, потом глоссарий — якорь не трогаем.
    if ctx:
        overflow = len(prompt) - _PROMPT_BUDGET_CHARS
        ctx_trimmed = ctx[overflow + 3 :].lstrip(" ,.;")
        parts[-1] = f"Контекст: …{ctx_trimmed}" if ctx_trimmed else ""
        parts = [p for p in parts if p]
        prompt = " ".join(parts)
    if len(prompt) > _PROMPT_BUDGET_CHARS and g:
        keep = _PROMPT_BUDGET_CHARS - len(_RU_ANCHOR_PROMPT) - len(" Участники и термины: ")
        if keep > 0:
            parts[1] = f"Участники и термины: {g[:keep].rstrip(', ')}"
            prompt = " ".join(p for p in parts if p)
    return prompt[:_PROMPT_BUDGET_CHARS]


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


def _preprocess_audio(src: Path) -> Path:
    """Денойз + ресемплинг в 16 kHz mono перед Whisper.

    Возвращает путь к обработанному WAV (во временной папке) или исходник,
    если ffmpeg недоступен / препроцессинг отключён / упала команда.
    Вызывающий обязан удалить результат, если он отличается от src.
    """
    if not DENOISE or not _have_ffmpeg():
        return src
    tmp_dir = Path(tempfile.mkdtemp(prefix="dn_"))
    out = tmp_dir / (src.stem + "_dn.wav")
    # highpass=80 — режем гул вентиляторов / 50 Гц.
    # afftdn=nr=12 — спектральный денойз.
    # loudnorm — EBU R128, спокойнее dynaudnorm: не пережимает паузы и не
    #   вытягивает шум до уровня речи на тихих участках.
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-af", "highpass=f=80,afftdn=nr=12,loudnorm=I=-16:LRA=11:TP=-1.5",
        "-ac", "1", "-ar", "16000",
        "-loglevel", "error",
        str(out),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        return out
    except Exception:
        # ffmpeg не отработал — снос tmp_dir, чтобы не копился мусор в %TEMP%.
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return src


def _cleanup_preprocessed(orig: Path, processed: Path) -> None:
    if processed == orig:
        return
    try:
        processed.unlink(missing_ok=True)
        processed.parent.rmdir()
    except Exception:
        pass


def _normalize_words(words) -> list[dict[str, Any]]:
    """Привести список слов из mlx/faster к единому виду."""
    out: list[dict[str, Any]] = []
    for w in words or []:
        if isinstance(w, dict):
            text = str(w.get("word", ""))
            start = float(w.get("start", 0.0))
            end = float(w.get("end", 0.0))
        else:
            # faster-whisper Word: .word, .start, .end
            text = str(getattr(w, "word", ""))
            start = float(getattr(w, "start", 0.0) or 0.0)
            end = float(getattr(w, "end", 0.0) or 0.0)
        if not text:
            continue
        out.append({"word": text, "start": start, "end": end})
    return out


def _filter_segments(raw_segments) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    last_text = ""
    for s in raw_segments:
        text = str(s.get("text", "")).strip()
        if not text or _is_hallucination(text) or text == last_text:
            continue
        out.append({
            "start": float(s.get("start", 0.0)),
            "end": float(s.get("end", 0.0)),
            "text": text,
            "words": s.get("words", []),
        })
        last_text = text
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
        import torch
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

        pieces = [wav[t["start"]:t["end"]] for t in ts]
        offsets: list[tuple[float, float]] = []
        cum_samples = 0
        for t, piece in zip(ts, pieces):
            offsets.append((cum_samples / 16000.0, t["start"] / 16000.0))
            cum_samples += piece.shape[0]
        concat = torch.cat(pieces)

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
    wav_path: Path,
    language: str | None,
    glossary: str | None = None,
    prev_context: str | None = None,
) -> dict[str, Any]:
    import mlx_whisper

    ensure_local_whisper(
        lambda msg: print(f"[ASR] {msg}", file=sys.stderr, flush=True)
    )
    status, speech_wav, offsets = _silero_extract_speech(wav_path)
    if status == "empty":
        return {"text": "", "segments": [], "language": language}
    source = speech_wav if status == "ok" else wav_path

    pre = _preprocess_audio(Path(source))
    t0 = time.monotonic()
    print(
        f"[ASR] Транскрибация аудио (модель локально, {whisper_model_ref()})...",
        file=sys.stderr, flush=True,
    )
    try:
        # mlx-whisper НЕ поддерживает beam_search (NotImplementedError),
        # поэтому ограничиваемся temperature fallback + no_speech_threshold.
        # Beam-параметры используются только в faster-whisper.
        result = mlx_whisper.transcribe(
            str(pre),
            path_or_hf_repo=whisper_model_ref(),
            language=language,
            task="transcribe",
            word_timestamps=True,
            initial_prompt=_build_initial_prompt(glossary, prev_context),
            condition_on_previous_text=False,
            temperature=_ASR_TEMPERATURES,
            # Чуть жёстче режем «ничегонесказал» сегменты — на шумной записи
            # снижает галлюцинации на тишине.
            no_speech_threshold=0.6,
            verbose=False,
        )
    finally:
        _cleanup_preprocessed(Path(source), pre)
        if speech_wav is not None:
            _cleanup_preprocessed(wav_path, speech_wav)
        print(
            f"[ASR] Транскрибация завершена за {time.monotonic() - t0:.1f}s",
            file=sys.stderr, flush=True,
        )
    segments = result.get("segments", []) or []
    for s in segments:
        s["words"] = _normalize_words(s.get("words"))
    if status == "ok" and offsets:
        for s in segments:
            s["start"] = _remap_time(float(s.get("start", 0.0)), offsets)
            s["end"] = _remap_time(float(s.get("end", 0.0)), offsets)
            for w in s["words"]:
                w["start"] = _remap_time(w["start"], offsets)
                w["end"] = _remap_time(w["end"], offsets)
    return {
        "text": (result.get("text") or "").strip(),
        "segments": segments,
        "language": result.get("language", language),
    }


# ---------- faster-whisper backend (Windows / CPU) ---------------------------

_faster_model = None
_faster_lock = threading.Lock()
_faster_device = None  # реально использованное устройство ("cuda" / "cpu")


def _is_cuda_runtime_error(err: BaseException) -> bool:
    msg = str(err).lower()
    return any(
        s in msg
        for s in ("cudnn", "cublas", "cuda", "cudart", "no cuda-capable")
    )


def _faster_load(device: str, compute_type: str):
    from faster_whisper import WhisperModel

    return WhisperModel(
        whisper_model_ref(),
        device=device,
        compute_type=compute_type,
    )


def _faster_get_model():
    global _faster_model, _faster_device
    if _faster_model is not None:
        return _faster_model
    with _faster_lock:
        if _faster_model is not None:
            return _faster_model
        ensure_local_whisper(
            lambda msg: print(f"[ASR] {msg}", file=sys.stderr, flush=True)
        )
        try:
            _faster_model = _faster_load(ASR_DEVICE, ASR_COMPUTE_TYPE)
            _faster_device = ASR_DEVICE
        except Exception as e:  # noqa: BLE001
            if ASR_DEVICE != "cpu" and _is_cuda_runtime_error(e):
                print(
                    f"[ASR] CUDA недоступна ({e}). Переключаюсь на CPU (int8).",
                    file=sys.stderr, flush=True,
                )
                _faster_model = _faster_load("cpu", "int8")
                _faster_device = "cpu"
            else:
                raise
    return _faster_model


def _faster_reload_cpu_after_runtime_error() -> None:
    """Если CUDA-библиотеки нашлись для load(), но упали на inference (например,
    нет cuDNN) — перезагружаем модель на CPU и повторяем."""
    global _faster_model, _faster_device
    with _faster_lock:
        _faster_model = _faster_load("cpu", "int8")
        _faster_device = "cpu"


def _faster_transcribe(
    wav_path: Path,
    language: str | None,
    glossary: str | None = None,
    prev_context: str | None = None,
) -> dict[str, Any]:
    model = _faster_get_model()
    pre = _preprocess_audio(Path(wav_path))
    t0 = time.monotonic()
    print(
        f"[ASR] Транскрибация аудио (модель локально, {whisper_model_ref()})...",
        file=sys.stderr, flush=True,
    )

    def _run_transcribe(m):
        segments_iter, info = m.transcribe(
            str(pre),
            language=language,
            task="transcribe",
            initial_prompt=_build_initial_prompt(glossary, prev_context),
            condition_on_previous_text=False,
            word_timestamps=True,
            # Beam search: 10 кандидатов вместо 5 + patience=2 — точнее на
            # сложных русских словах, ~1.3-1.5× медленнее.
            beam_size=10,
            best_of=5,
            patience=2.0,
            temperature=_ASR_TEMPERATURES,
            no_speech_threshold=0.6,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            hotwords=(glossary or None),
        )
        return [
            {
                "start": float(s.start),
                "end": float(s.end),
                "text": (s.text or "").strip(),
                "words": _normalize_words(getattr(s, "words", None)),
            }
            for s in segments_iter
        ], info

    try:
        try:
            segs, info = _run_transcribe(model)
        except Exception as e:  # noqa: BLE001
            if _faster_device != "cpu" and _is_cuda_runtime_error(e):
                print(
                    f"[ASR] Сбой CUDA-инференса ({e}). Перезагружаю модель на CPU.",
                    file=sys.stderr, flush=True,
                )
                _faster_reload_cpu_after_runtime_error()
                segs, info = _run_transcribe(_faster_get_model())
            else:
                raise
    finally:
        _cleanup_preprocessed(Path(wav_path), pre)
        print(
            f"[ASR] Транскрибация завершена за {time.monotonic() - t0:.1f}s",
            file=sys.stderr, flush=True,
        )
    text = " ".join(s["text"] for s in segs).strip()
    return {"text": text, "segments": segs, "language": info.language or language}


# ---------- единый интерфейс -------------------------------------------------

def _backend_transcribe(
    wav_path: Path,
    language: str | None,
    glossary: str | None = None,
    prev_context: str | None = None,
) -> dict[str, Any]:
    if ASR_BACKEND == "mlx":
        return _mlx_transcribe(wav_path, language, glossary, prev_context)
    return _faster_transcribe(wav_path, language, glossary, prev_context)


def transcribe_chunk(
    wav_path: Path,
    language: str | None = "ru",
    glossary: str | None = None,
    prev_context: str | None = None,
) -> list[dict[str, Any]]:
    """Транскрибация одного чанка.

    `prev_context` — последние слова предыдущего чанка (после фильтрации
    галлюцинаций); подмешиваются в initial_prompt для связности на стыках.
    """
    result = _backend_transcribe(Path(wav_path), language, glossary, prev_context)
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

    result = _backend_transcribe(wav, language, glossary, prev_context=None)

    if progress_cb:
        progress_cb("asr:done", 1.0)

    return {
        "text": result["text"],
        "segments": _filter_segments(result["segments"]),
        "language": result.get("language", language),
    }
