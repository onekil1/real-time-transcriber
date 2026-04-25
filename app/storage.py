from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterable

from .config import DB_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    started_at    REAL NOT NULL,
    ended_at      REAL,
    duration_sec  REAL,
    audio_path    TEXT,
    source        TEXT NOT NULL DEFAULT 'mic',   -- 'mic' | 'upload'
    status        TEXT NOT NULL DEFAULT 'new',   -- new|recording|transcribing|summarizing|done|error
    template      TEXT NOT NULL DEFAULT 'meeting',
    glossary      TEXT NOT NULL DEFAULT '',
    error         TEXT
);

CREATE TABLE IF NOT EXISTS segments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    idx         INTEGER NOT NULL,
    start_sec   REAL NOT NULL,
    end_sec     REAL NOT NULL,
    text        TEXT NOT NULL,
    speaker     TEXT
);

CREATE INDEX IF NOT EXISTS ix_segments_session ON segments(session_id, idx);

CREATE TABLE IF NOT EXISTS reports (
    session_id  TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    md          TEXT NOT NULL DEFAULT '',
    data        TEXT NOT NULL DEFAULT '{}',     -- JSON
    updated_at  REAL NOT NULL
);
"""


@contextmanager
def _conn():
    ensure_dirs()
    cx = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    cx.row_factory = sqlite3.Row
    cx.execute("PRAGMA foreign_keys = ON;")
    cx.execute("PRAGMA journal_mode = WAL;")
    try:
        yield cx
    finally:
        cx.close()


def init_db() -> None:
    with _conn() as cx:
        cx.executescript(SCHEMA)
        # миграция: добавить template в старые БД
        cols = {r["name"] for r in cx.execute("PRAGMA table_info(sessions)").fetchall()}
        if "template" not in cols:
            cx.execute(
                "ALTER TABLE sessions ADD COLUMN template TEXT NOT NULL DEFAULT 'meeting'"
            )
        if "glossary" not in cols:
            cx.execute(
                "ALTER TABLE sessions ADD COLUMN glossary TEXT NOT NULL DEFAULT ''"
            )
        cx.execute(
            "UPDATE sessions SET status='error', error='Сервер перезапущен во время обработки' "
            "WHERE status IN ('recording','transcribing','summarizing','new')"
        )


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def create_session(title: str, source: str = "mic", template: str = "meeting") -> str:
    sid = uuid.uuid4().hex[:12]
    with _conn() as cx:
        cx.execute(
            "INSERT INTO sessions(id, title, started_at, source, status, template) "
            "VALUES(?,?,?,?,?,?)",
            (sid, title, time.time(), source, "new", template),
        )
    return sid


def update_template(session_id: str, template: str) -> None:
    with _conn() as cx:
        cx.execute("UPDATE sessions SET template=? WHERE id=?", (template, session_id))


def update_title(session_id: str, title: str) -> None:
    with _conn() as cx:
        cx.execute("UPDATE sessions SET title=? WHERE id=?", (title, session_id))


def set_status(session_id: str, status: str, error: str | None = None) -> None:
    with _conn() as cx:
        cx.execute(
            "UPDATE sessions SET status=?, error=? WHERE id=?",
            (status, error, session_id),
        )


def set_audio(session_id: str, audio_path: str, duration_sec: float | None) -> None:
    with _conn() as cx:
        cx.execute(
            "UPDATE sessions SET audio_path=?, duration_sec=?, ended_at=? WHERE id=?",
            (audio_path, duration_sec, time.time(), session_id),
        )


def append_segments(session_id: str, segments: Iterable[dict[str, Any]]) -> int:
    """Добавить сегменты в конец (реалтайм). Возвращает количество добавленных."""
    segs = list(segments)
    if not segs:
        return 0
    with _conn() as cx:
        cur = cx.execute(
            "SELECT COALESCE(MAX(idx), -1) FROM segments WHERE session_id=?",
            (session_id,),
        ).fetchone()
        next_idx = (cur[0] if cur and cur[0] is not None else -1) + 1
        rows = [
            (
                session_id,
                next_idx + i,
                float(s.get("start", 0.0)),
                float(s.get("end", 0.0)),
                str(s.get("text", "")).strip(),
                s.get("speaker"),
            )
            for i, s in enumerate(segs)
        ]
        cx.executemany(
            "INSERT INTO segments(session_id, idx, start_sec, end_sec, text, speaker) "
            "VALUES (?,?,?,?,?,?)",
            rows,
        )
    return len(rows)


def last_segment_end(session_id: str) -> float:
    with _conn() as cx:
        row = cx.execute(
            "SELECT MAX(end_sec) FROM segments WHERE session_id=?", (session_id,)
        ).fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def save_segments(session_id: str, segments: Iterable[dict[str, Any]]) -> None:
    rows = []
    for i, s in enumerate(segments):
        rows.append(
            (
                session_id,
                i,
                float(s.get("start", 0.0)),
                float(s.get("end", 0.0)),
                str(s.get("text", "")).strip(),
                s.get("speaker"),
            )
        )
    # Соединение в autocommit (isolation_level=None), поэтому DELETE+INSERT
    # без явной транзакции — два независимых коммита: при сбое insert-а
    # старые сегменты уже удалены и не вернутся. Заворачиваем в BEGIN/COMMIT.
    with _conn() as cx:
        cx.execute("BEGIN")
        try:
            cx.execute("DELETE FROM segments WHERE session_id=?", (session_id,))
            cx.executemany(
                "INSERT INTO segments(session_id, idx, start_sec, end_sec, text, speaker) "
                "VALUES (?,?,?,?,?,?)",
                rows,
            )
            cx.execute("COMMIT")
        except Exception:
            cx.execute("ROLLBACK")
            raise


def save_report(session_id: str, md: str, data: dict[str, Any]) -> None:
    with _conn() as cx:
        cx.execute(
            "INSERT INTO reports(session_id, md, data, updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET md=excluded.md, data=excluded.data, "
            "updated_at=excluded.updated_at",
            (session_id, md, json.dumps(data, ensure_ascii=False), time.time()),
        )


def update_report_md(session_id: str, md: str) -> None:
    with _conn() as cx:
        cx.execute(
            "UPDATE reports SET md=?, updated_at=? WHERE session_id=?",
            (md, time.time(), session_id),
        )


def list_sessions() -> list[dict[str, Any]]:
    with _conn() as cx:
        rows = cx.execute(
            "SELECT id, title, started_at, ended_at, duration_sec, source, status, template "
            "FROM sessions ORDER BY started_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_session(session_id: str) -> dict[str, Any] | None:
    with _conn() as cx:
        row = cx.execute(
            "SELECT * FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        segs = cx.execute(
            "SELECT idx, start_sec, end_sec, text, speaker FROM segments "
            "WHERE session_id=? ORDER BY idx",
            (session_id,),
        ).fetchall()
        rep = cx.execute(
            "SELECT md, data, updated_at FROM reports WHERE session_id=?",
            (session_id,),
        ).fetchone()

    out = dict(row)
    out["segments"] = [dict(s) for s in segs]
    if rep is not None:
        out["report"] = {
            "md": rep["md"],
            "data": json.loads(rep["data"] or "{}"),
            "updated_at": rep["updated_at"],
        }
    else:
        out["report"] = None
    return out


def delete_session(session_id: str) -> None:
    with _conn() as cx:
        cx.execute("DELETE FROM sessions WHERE id=?", (session_id,))


def full_transcript_text(session_id: str) -> str:
    with _conn() as cx:
        rows = cx.execute(
            "SELECT text FROM segments WHERE session_id=? ORDER BY idx",
            (session_id,),
        ).fetchall()
    return "\n".join(r["text"] for r in rows if r["text"])
