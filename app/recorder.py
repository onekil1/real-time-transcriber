from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf

from .config import AUDIO_DIR, CHANNELS, SAMPLE_RATE, ensure_dirs

# Настройки чанкера реалтайма
CHUNK_SEC = 30
OVERLAP_SEC = 2


class ChunkInfo:
    __slots__ = ("session_id", "idx", "path", "start_sec", "end_sec")

    def __init__(self, session_id: str, idx: int, path: Path, start_sec: float, end_sec: float):
        self.session_id = session_id
        self.idx = idx
        self.path = path
        self.start_sec = start_sec
        self.end_sec = end_sec


class Recorder:
    """Потоковая запись с микрофона + ротация чанков для реалтайм-транскрибации.

    - Пишет полный master WAV в audio/<sid>.wav
    - Параллельно пишет чанки 30с (с 2с overlap) в audio/chunks/<sid>/<idx>.wav
    - Готовые чанки складывает в self.chunk_queue
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stream: Optional[sd.InputStream] = None
        self._master_sf: Optional[sf.SoundFile] = None
        self._chunk_sf: Optional[sf.SoundFile] = None

        self._session_id: Optional[str] = None
        self._master_path: Optional[Path] = None
        self._chunks_dir: Optional[Path] = None

        self._frame_q: queue.Queue = queue.Queue()
        self._writer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self.chunk_queue: queue.Queue[ChunkInfo | None] = queue.Queue()

        self._started_at: Optional[float] = None
        self._total_frames: int = 0

    # -------- public API --------

    @property
    def active(self) -> bool:
        return self._stream is not None

    @property
    def current_session(self) -> Optional[str]:
        return self._session_id

    def elapsed(self) -> float:
        return time.time() - self._started_at if self._started_at else 0.0

    def start(self, session_id: str) -> Path:
        with self._lock:
            if self._stream is not None:
                raise RuntimeError("Запись уже идёт")
            ensure_dirs()

            self._session_id = session_id
            self._master_path = AUDIO_DIR / f"{session_id}.wav"
            self._chunks_dir = AUDIO_DIR / "chunks" / session_id
            self._chunks_dir.mkdir(parents=True, exist_ok=True)

            # очистим очереди
            self._frame_q = queue.Queue()
            self.chunk_queue = queue.Queue()
            self._stop_event.clear()

            self._master_sf = sf.SoundFile(
                str(self._master_path), mode="w",
                samplerate=SAMPLE_RATE, channels=CHANNELS, subtype="PCM_16",
            )

            self._started_at = time.time()
            self._total_frames = 0

            self._writer_thread = threading.Thread(
                target=self._writer_loop, daemon=True, name="scribe-writer"
            )
            self._writer_thread.start()

            def cb(indata, frames, time_info, status):  # noqa: ARG001
                # Callback аудиопотока. НЕ делаем тут I/O — только складываем в очередь.
                try:
                    self._frame_q.put_nowait(indata.copy())
                except queue.Full:
                    pass

            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                callback=cb,
                blocksize=0,
            )
            self._stream.start()
            return self._master_path

    def stop(self) -> tuple[Path, float]:
        with self._lock:
            if self._stream is None or self._master_path is None:
                raise RuntimeError("Запись не запущена")
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None

            # Дать writer-потоку слить остаток очереди
            self._stop_event.set()
            if self._writer_thread is not None:
                self._writer_thread.join(timeout=5)
                self._writer_thread = None

            if self._master_sf is not None:
                self._master_sf.close()
                self._master_sf = None
            if self._chunk_sf is not None:
                self._chunk_sf.close()
                self._chunk_sf = None

            # Сигнал потребителю, что чанков больше не будет
            self.chunk_queue.put(None)

            duration = self._total_frames / SAMPLE_RATE
            path = self._master_path

            self._master_path = None
            self._chunks_dir = None
            self._session_id = None
            self._started_at = None
            self._total_frames = 0
            return path, duration

    # -------- writer thread --------

    def _writer_loop(self) -> None:
        assert self._chunks_dir is not None and self._master_sf is not None

        chunk_idx = 0
        chunk_started_frame = 0
        chunk_frames_written = 0
        chunk_path = self._chunks_dir / f"{chunk_idx:04d}.wav"
        self._chunk_sf = sf.SoundFile(
            str(chunk_path), mode="w",
            samplerate=SAMPLE_RATE, channels=CHANNELS, subtype="PCM_16",
        )

        chunk_frames_target = int(CHUNK_SEC * SAMPLE_RATE)
        overlap_frames = int(OVERLAP_SEC * SAMPLE_RATE)

        # Кольцевой буфер последних 2с для seed'а следующего чанка
        ring = np.zeros((overlap_frames, CHANNELS), dtype="int16")
        ring_pos = 0

        while not (self._stop_event.is_set() and self._frame_q.empty()):
            try:
                block = self._frame_q.get(timeout=0.1)
            except queue.Empty:
                continue

            # master
            self._master_sf.write(block)

            # chunk
            self._chunk_sf.write(block)
            chunk_frames_written += block.shape[0]
            self._total_frames += block.shape[0]

            # обновим ring
            n = block.shape[0]
            if n >= overlap_frames:
                ring = block[-overlap_frames:].copy()
                ring_pos = 0
            else:
                take = overlap_frames - n
                ring = np.concatenate([ring[-take:], block], axis=0)

            # пора закрывать чанк?
            if chunk_frames_written >= chunk_frames_target:
                self._chunk_sf.close()
                start_sec = chunk_started_frame / SAMPLE_RATE
                end_sec = (chunk_started_frame + chunk_frames_written) / SAMPLE_RATE
                self.chunk_queue.put(
                    ChunkInfo(self._session_id or "", chunk_idx, chunk_path, start_sec, end_sec)
                )

                chunk_idx += 1
                chunk_path = self._chunks_dir / f"{chunk_idx:04d}.wav"
                self._chunk_sf = sf.SoundFile(
                    str(chunk_path), mode="w",
                    samplerate=SAMPLE_RATE, channels=CHANNELS, subtype="PCM_16",
                )
                # Seed нового чанка последними overlap_frames из ring
                self._chunk_sf.write(ring)
                # Следующий чанк реально стартует раньше на OVERLAP_SEC
                chunk_started_frame = (
                    chunk_started_frame + chunk_frames_written - overlap_frames
                )
                chunk_frames_written = overlap_frames

        # финальный чанк (последний, может быть короче)
        if self._chunk_sf is not None and chunk_frames_written > 0:
            self._chunk_sf.close()
            self._chunk_sf = None
            if chunk_frames_written > int(1.0 * SAMPLE_RATE):  # не меньше секунды
                start_sec = chunk_started_frame / SAMPLE_RATE
                end_sec = (chunk_started_frame + chunk_frames_written) / SAMPLE_RATE
                self.chunk_queue.put(
                    ChunkInfo(self._session_id or "", chunk_idx, chunk_path, start_sec, end_sec)
                )


recorder = Recorder()


def wav_duration(path: Path) -> float:
    with sf.SoundFile(str(path)) as f:
        return len(f) / f.samplerate
