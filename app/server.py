from __future__ import annotations

import asyncio
import shutil
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from . import storage
from .config import AUDIO_DIR, WEB_DIR, ensure_dirs
from .events import bus
from .recorder import recorder, wav_duration

app = FastAPI(title="Meeting Scribe", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- модели -------------------------------------------------

class StartRequest(BaseModel):
    title: str | None = None
    template: str | None = None


class ReportPatch(BaseModel):
    md: str


class TitlePatch(BaseModel):
    title: str | None = None
    template: str | None = None


class GlossaryPatch(BaseModel):
    text: str = ""


# ---------- активность (для UI-индикаторов) ------------------------

_activity_lock = threading.Lock()
_activity: dict[str, int] = {"whisper": 0, "llm": 0}
_activity_session: dict[str, str | None] = {"whisper": None, "llm": None}


@contextmanager
def _busy(kind: str, session_id: str | None = None):
    with _activity_lock:
        _activity[kind] += 1
        _activity_session[kind] = session_id
    try:
        yield
    finally:
        with _activity_lock:
            _activity[kind] -= 1
            if _activity[kind] == 0:
                _activity_session[kind] = None


# ---------- старт/стоп записи --------------------------------------

@app.on_event("startup")
async def _startup() -> None:
    ensure_dirs()
    storage.init_db()
    bus.attach_loop(asyncio.get_running_loop())


@app.post("/api/sessions/start")
async def start_recording(req: StartRequest):
    if recorder.active:
        raise HTTPException(409, "Запись уже идёт")
    from . import summarize as summ

    base = (req.title or "").strip() or "Совещание"
    stamp = datetime.now().strftime("%d.%m.%Y %H:%M")
    title = f"{base} {stamp}"
    tmpl = req.template if req.template in summ.TEMPLATES else summ.DEFAULT_TEMPLATE
    sid = storage.create_session(title=title, source="mic", template=tmpl)
    recorder.start(sid)
    storage.set_status(sid, "recording")
    bus.publish(sid, "recording", 0.0)
    asyncio.create_task(_live_mic_pipeline(sid))
    return {"id": sid, "status": "recording"}


@app.post("/api/sessions/{session_id}/stop")
async def stop_recording(session_id: str):
    if not recorder.active or recorder.current_session != session_id:
        raise HTTPException(409, "Нет активной записи для этой сессии")
    path, duration = recorder.stop()
    storage.set_audio(session_id, str(path), duration)
    bus.publish(session_id, "recording:stopped", None, duration=duration)
    return {"id": session_id, "status": "transcribing", "duration_sec": duration}


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    template: str | None = Form(None),
):
    if not file.filename:
        raise HTTPException(400, "Пустое имя файла")
    from . import summarize as summ

    tmpl = template if template in summ.TEMPLATES else summ.DEFAULT_TEMPLATE
    sid = storage.create_session(
        title=(title or Path(file.filename).stem).strip(),
        source="upload",
        template=tmpl,
    )
    ensure_dirs()
    dest = AUDIO_DIR / f"{sid}{Path(file.filename).suffix.lower()}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        dur = wav_duration(dest) if dest.suffix == ".wav" else None
    except Exception:
        dur = None
    storage.set_audio(sid, str(dest), dur)
    storage.set_status(sid, "transcribing")
    bus.publish(sid, "uploaded", 1.0)
    asyncio.create_task(_process_session(sid, dest))
    return {"id": sid, "status": "transcribing"}


# ---------- live pipeline (mic) ------------------------------------

async def _live_mic_pipeline(session_id: str) -> None:
    """Запускается вместе со start_recording.

    1. Крутит чанковый консюмер (executor-поток) — он транскрибирует чанки
       в реалтайме, дописывает сегменты в БД, публикует SSE `asr:partial`.
    2. Когда recorder.stop() кладёт None в очередь — консюмер завершается.
    3. Далее гоним отчёт через LM Studio.
    """
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, _consume_chunks, session_id)
        # чанки кончились → запись остановлена и транскрипт готов
        storage.set_status(session_id, "summarizing")
        bus.publish(session_id, "summarizing", None)
        await _summarize(session_id)
        storage.set_status(session_id, "done")
        bus.publish(session_id, "done", 1.0)
    except Exception as e:  # noqa: BLE001
        storage.set_status(session_id, "error", error=str(e))
        bus.publish(session_id, "error", 1.0, message=str(e))


def _consume_chunks(session_id: str) -> None:
    """Синхронный потребитель чанков из recorder.chunk_queue.
    Работает в executor-потоке, чтобы не блокировать event loop."""
    from . import settings, transcribe

    glossary = settings.get_glossary()
    processed = 0
    while True:
        item = recorder.chunk_queue.get()
        if item is None:
            break
        if item.session_id != session_id:
            continue

        bus.publish(session_id, "asr:chunk_start", None, chunk=item.idx)
        with _busy("whisper", session_id):
            segs = transcribe.transcribe_chunk(item.path, glossary=glossary)
        abs_segs = [
            {
                "start": item.start_sec + s["start"],
                "end": item.start_sec + s["end"],
                "text": s["text"],
                "words": [
                    {
                        "word": w["word"],
                        "start": item.start_sec + w["start"],
                        "end": item.start_sec + w["end"],
                    }
                    for w in s.get("words", [])
                ],
            }
            for s in segs
        ]
        last_end = storage.last_segment_end(session_id)
        new_segs = _dedup_overlap(abs_segs, last_end)

        if new_segs:
            storage.append_segments(session_id, new_segs)
            added_text = " ".join(s["text"] for s in new_segs)
            bus.publish(
                session_id,
                "asr:partial",
                None,
                text=added_text,
                start=new_segs[0]["start"],
                chunk=item.idx,
            )

        processed += 1
        bus.publish(session_id, "asr:chunk_done", None, chunk=item.idx, processed=processed)

        try:
            item.path.unlink(missing_ok=True)
        except Exception:
            pass

    # почистим папку чанков
    try:
        chunks_dir = item.path.parent if item is not None else None
        if chunks_dir and chunks_dir.exists():
            chunks_dir.rmdir()
    except Exception:
        pass


def _dedup_overlap(segs: list[dict[str, Any]], last_end: float) -> list[dict[str, Any]]:
    """Отрезать у каждого сегмента слова, начавшиеся раньше last_end (зона overlap'а),
    и собрать чистый текст. Если у сегмента нет word-таймингов — fallback на старое
    правило по концу сегмента."""
    TOL = 0.15
    out: list[dict[str, Any]] = []
    for s in segs:
        if not s.get("text"):
            continue
        words = s.get("words") or []
        if not words:
            if s["end"] > last_end + 0.1:
                out.append({"start": s["start"], "end": s["end"], "text": s["text"]})
            continue
        kept = [w for w in words if w["start"] >= last_end - TOL]
        if not kept:
            continue
        text = "".join(w["word"] for w in kept).strip()
        if not text:
            continue
        out.append({"start": kept[0]["start"], "end": kept[-1]["end"], "text": text})
    return out


async def _summarize(session_id: str) -> None:
    from . import summarize as summ

    loop = asyncio.get_running_loop()

    def llm_progress(evt: str, prog: float, **kw):
        bus.publish(session_id, evt, prog, **kw)

    text = storage.full_transcript_text(session_id)
    if not text.strip():
        storage.save_report(session_id, md="_Транскрипт пуст_", data={})
        return
    sess = storage.get_session(session_id) or {}
    tmpl = sess.get("template") or summ.DEFAULT_TEMPLATE

    def _run_llm():
        with _busy("llm", session_id):
            return summ.generate_report(text, progress_cb=llm_progress, template=tmpl)

    report = await loop.run_in_executor(None, _run_llm)
    storage.save_report(session_id, md=report["md"], data=report["data"])


# ---------- фоновая обработка (upload, пакетно) --------------------

async def _process_session(session_id: str, audio_path: Path) -> None:
    from . import settings, summarize, transcribe

    loop = asyncio.get_running_loop()

    def asr_progress(evt: str, prog: float):
        bus.publish(session_id, evt, prog)

    try:
        bus.publish(session_id, "transcribing", 0.1)

        glossary = settings.get_glossary()

        def _run_asr():
            with _busy("whisper", session_id):
                return transcribe.transcribe_file(
                    audio_path, progress_cb=asr_progress, glossary=glossary
                )

        result = await loop.run_in_executor(None, _run_asr)
        storage.save_segments(session_id, result["segments"])

        bus.publish(session_id, "summarizing", 0.6)
        storage.set_status(session_id, "summarizing")

        def llm_progress(evt: str, prog: float, extra: dict | None = None):
            bus.publish(session_id, evt, prog, **(extra or {}))

        text = storage.full_transcript_text(session_id) or result.get("text", "")
        sess = storage.get_session(session_id) or {}
        tmpl = sess.get("template") or summarize.DEFAULT_TEMPLATE

        def _run_llm():
            with _busy("llm", session_id):
                return summarize.generate_report(text, progress_cb=llm_progress, template=tmpl)

        report = await loop.run_in_executor(None, _run_llm)
        storage.save_report(session_id, md=report["md"], data=report["data"])
        storage.set_status(session_id, "done")
        bus.publish(session_id, "done", 1.0)
    except Exception as e:  # noqa: BLE001
        storage.set_status(session_id, "error", error=str(e))
        bus.publish(session_id, "error", 1.0, message=str(e))


# ---------- чтение -------------------------------------------------

@app.get("/api/sessions")
def sessions():
    return storage.list_sessions()


@app.get("/api/sessions/{session_id}")
def session_detail(session_id: str):
    s = storage.get_session(session_id)
    if s is None:
        raise HTTPException(404, "Сессия не найдена")
    return s


@app.get("/api/sessions/{session_id}/audio")
def session_audio(session_id: str):
    s = storage.get_session(session_id)
    if s is None or not s.get("audio_path"):
        raise HTTPException(404)
    return FileResponse(s["audio_path"])


@app.patch("/api/sessions/{session_id}")
def patch_session(session_id: str, patch: TitlePatch):
    from . import summarize as summ

    s = storage.get_session(session_id)
    if s is None:
        raise HTTPException(404, "Сессия не найдена")
    out: dict[str, Any] = {"ok": True}
    if patch.title is not None:
        title = patch.title.strip() or "Без названия"
        storage.update_title(session_id, title)
        out["title"] = title
    if patch.template is not None:
        if patch.template not in summ.TEMPLATES:
            raise HTTPException(400, "Неизвестный шаблон")
        storage.update_template(session_id, patch.template)
        out["template"] = patch.template
    return out


@app.get("/api/glossary")
def glossary_get():
    from . import settings
    return {"text": settings.get_glossary()}


@app.put("/api/glossary")
def glossary_put(patch: GlossaryPatch):
    from . import settings
    settings.set_glossary(patch.text)
    return {"ok": True, "text": settings.get_glossary()}


@app.patch("/api/sessions/{session_id}/report")
def patch_report(session_id: str, patch: ReportPatch):
    s = storage.get_session(session_id)
    if s is None:
        raise HTTPException(404)
    if s.get("report") is None:
        storage.save_report(session_id, md=patch.md, data={})
    else:
        storage.update_report_md(session_id, patch.md)
    return {"ok": True}


@app.post("/api/sessions/{session_id}/regenerate")
async def regenerate_report(session_id: str):
    s = storage.get_session(session_id)
    if s is None:
        raise HTTPException(404, "Сессия не найдена")
    storage.set_status(session_id, "summarizing")
    bus.publish(session_id, "summarizing", None)

    async def _run():
        try:
            await _summarize(session_id)
            storage.set_status(session_id, "done")
            bus.publish(session_id, "done", 1.0)
        except Exception as e:  # noqa: BLE001
            storage.set_status(session_id, "error", error=str(e))
            bus.publish(session_id, "error", 1.0, message=str(e))

    asyncio.create_task(_run())
    return {"ok": True}


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    storage.delete_session(session_id)
    return {"ok": True}


@app.get("/api/sessions/{session_id}/events")
async def events(session_id: str):
    q = bus.subscribe(session_id)

    async def gen():
        try:
            while True:
                payload = await q.get()
                yield {"data": _json(payload)}
                if payload.get("event") in {"done", "error"}:
                    break
        finally:
            bus.unsubscribe(session_id, q)

    return EventSourceResponse(gen())


@app.get("/api/status")
def status():
    with _activity_lock:
        whisper_busy = _activity["whisper"] > 0
        llm_busy = _activity["llm"] > 0
        whisper_session = _activity_session["whisper"]
        llm_session = _activity_session["llm"]
    return {
        "recording": recorder.active,
        "session_id": recorder.current_session,
        "elapsed_sec": recorder.elapsed(),
        "whisper_busy": whisper_busy,
        "llm_busy": llm_busy,
        "whisper_session": whisper_session,
        "llm_session": llm_session,
    }


@app.post("/api/sessions/{session_id}/summarize-now")
async def summarize_now(session_id: str):
    """Саммери по текущему транскрипту без остановки записи."""
    with _activity_lock:
        if _activity["llm"] > 0:
            raise HTTPException(409, "LLM уже занят — попробуйте чуть позже")

    s = storage.get_session(session_id)
    if s is None:
        raise HTTPException(404, "Сессия не найдена")
    text = storage.full_transcript_text(session_id)
    if not text.strip():
        raise HTTPException(400, "Транскрипт пока пуст")

    from . import summarize as summ

    tmpl = s.get("template") or summ.DEFAULT_TEMPLATE
    loop = asyncio.get_running_loop()

    def llm_progress(evt: str, prog: float, **kw):
        bus.publish(session_id, evt, prog, **kw)

    async def _run():
        def _work():
            with _busy("llm", session_id):
                return summ.generate_report(text, progress_cb=llm_progress, template=tmpl)
        try:
            report = await loop.run_in_executor(None, _work)
            storage.save_report(session_id, md=report["md"], data=report["data"])
            bus.publish(session_id, "llm:done", 1.0)
        except Exception as e:  # noqa: BLE001
            bus.publish(session_id, "error", 1.0, message=str(e))

    asyncio.create_task(_run())
    return {"ok": True}


@app.get("/api/llm/ping")
def llm_ping():
    from . import summarize
    return summarize.ping()


@app.get("/api/templates")
def templates():
    from . import summarize
    return summarize.list_templates()


@app.get("/api/sessions/{session_id}/docx")
def session_docx(session_id: str):
    import io
    import re as _re
    from urllib.parse import quote

    from . import summarize

    s = storage.get_session(session_id)
    if s is None:
        raise HTTPException(404, "Сессия не найдена")
    doc = summarize.render_docx(
        report=s.get("report"),
        template_key=s.get("template"),
        title=s.get("title") or "Отчёт",
    )
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    safe = _re.sub(r"[^\w\-.а-яА-ЯёЁ ]", "_", s.get("title") or session_id).strip() or session_id
    fname = f"{safe}.docx"
    cd = f"attachment; filename=\"{session_id}.docx\"; filename*=UTF-8''{quote(fname)}"
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": cd},
    )


@app.get("/api/update/check")
def update_check():
    from . import updater
    return updater.check()


@app.post("/api/update/apply")
def update_apply():
    from . import updater
    return updater.apply()


@app.get("/api/health")
def health():
    from . import summarize, transcribe

    llm = summarize.ping()
    whisper = transcribe.model_info()
    return {
        "ok": bool(llm.get("ok")) and bool(whisper.get("ok")),
        "llm": llm,
        "whisper": whisper,
    }


def _json(obj: Any) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


# ---------- статика ------------------------------------------------

if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
else:
    @app.get("/")
    def _index():
        return JSONResponse({"ok": True, "hint": "web/ не найден"})
