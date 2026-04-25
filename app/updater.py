"""Проверка и установка обновлений из GitHub Releases.

Источник истины — последний релиз в репозитории `GITHUB_REPO`.
Применение обновления = `git pull` + `uv sync` в `PROJECT_ROOT`,
после чего пользователь должен вручную перезапустить приложение.
"""
from __future__ import annotations

import re
import subprocess
import threading
import time
from typing import Any

import requests

from .config import PROJECT_ROOT

# Таймауты для шагов обновления.
#   TOTAL — общий лимит на одну команду (для uv sync с большими DLL — щедро).
#   IDLE  — без вывода в stdout/stderr дольше этого = считаем зависшим.
_STEP_TOTAL_TIMEOUT_S = 900   # 15 минут
_STEP_IDLE_TIMEOUT_S = 180    # 3 минуты тишины

GITHUB_REPO = "onekil1/real-time-transcriber"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def current_version() -> str:
    try:
        from importlib.metadata import version

        return version("meeting-scribe")
    except Exception:
        # fallback — читаем из pyproject.toml
        pp = PROJECT_ROOT / "pyproject.toml"
        m = re.search(r'^version\s*=\s*"([^"]+)"', pp.read_text(encoding="utf-8"), re.M)
        return m.group(1) if m else "0.0.0"


def _parse(v: str) -> tuple[int, ...]:
    v = v.lstrip("vV").split("-", 1)[0].split("+", 1)[0]
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _is_newer(latest: str, current: str) -> bool:
    return _parse(latest) > _parse(current)


def check() -> dict[str, Any]:
    cur = current_version()
    try:
        r = requests.get(GITHUB_API, timeout=8, headers={"Accept": "application/vnd.github+json"})
        if r.status_code == 404:
            return {"current": cur, "latest": None, "available": False, "error": "релизов ещё нет"}
        r.raise_for_status()
        data = r.json()
    except Exception as e:  # noqa: BLE001
        return {"current": cur, "latest": None, "available": False, "error": str(e)}

    latest = (data.get("tag_name") or "").lstrip("vV")
    return {
        "current": cur,
        "latest": latest,
        "available": bool(latest) and _is_newer(latest, cur),
        "html_url": data.get("html_url"),
        "name": data.get("name"),
        "body": data.get("body") or "",
        "published_at": data.get("published_at"),
    }


_REMOTE_URL = f"https://github.com/{GITHUB_REPO}.git"
_DEFAULT_BRANCH = "main"


def _stream_command(cmd: list[str]):
    """Запускает команду и стримит её stdout/stderr построчно. Yield-ит:
      ("line", text) — строка вывода
      ("done", returncode) — выход

    Watchdog-тред убивает процесс, если: общее время > _STEP_TOTAL_TIMEOUT_S
    или нет вывода дольше _STEP_IDLE_TIMEOUT_S. На убитый процесс yield-им
    финальную строку с причиной — она увидится в логе UI.
    """
    p = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
    )
    assert p.stdout is not None

    started = time.monotonic()
    state = {"last": started, "killed_by": None}
    stop_evt = threading.Event()

    def _watchdog():
        while not stop_evt.wait(2.0):
            now = time.monotonic()
            if now - started > _STEP_TOTAL_TIMEOUT_S:
                state["killed_by"] = f"общий таймаут {_STEP_TOTAL_TIMEOUT_S}s"
                p.kill()
                return
            if now - state["last"] > _STEP_IDLE_TIMEOUT_S:
                state["killed_by"] = f"нет вывода {_STEP_IDLE_TIMEOUT_S}s"
                p.kill()
                return

    wd = threading.Thread(target=_watchdog, daemon=True)
    wd.start()

    try:
        for line in p.stdout:
            state["last"] = time.monotonic()
            yield ("line", line.rstrip("\r\n"))
    finally:
        stop_evt.set()
        try:
            p.stdout.close()
        except Exception:
            pass

    code = p.wait()
    if state["killed_by"]:
        yield ("line", f"[updater] процесс убит по таймауту: {state['killed_by']}")
    yield ("done", code)


def apply_stream():
    """Стримит прогресс обновления через события:
      {"type":"step",      "label": "git fetch origin main"}
      {"type":"line",      "text": "..."}                       # stdout/stderr
      {"type":"step_done", "label": "...", "code": 0}
      {"type":"done",      "ok": True/False, "step"?, "message": "..."}
    """
    git_dir = PROJECT_ROOT / ".git"

    # Контейнер для returncode из _run_step (yield не возвращает значение).
    rc_box = [0]

    def _run_step(cmd: list[str], label: str):
        yield {"type": "step", "label": label, "cmd": " ".join(cmd)}
        rc = 0
        for kind, payload in _stream_command(cmd):
            if kind == "line":
                yield {"type": "line", "text": payload}
            elif kind == "done":
                rc = payload
        yield {"type": "step_done", "label": label, "code": rc}
        rc_box[0] = rc

    if git_dir.exists():
        # 1) fetch
        yield from _run_step(["git", "fetch", "origin", _DEFAULT_BRANCH], "git fetch")
        if rc_box[0] != 0:
            yield {"type": "done", "ok": False, "step": "git fetch",
                   "message": f"git fetch завершился с кодом {rc_box[0]}"}
            return

        # 2) merge --ff-only; на конфликте (локальные правки tracked-файлов
        #    типа uv.lock) fallback на reset --hard. Untracked файлы
        #    (data/, .venv/, models/) reset не трогает.
        yield from _run_step(
            ["git", "merge", "--ff-only", f"origin/{_DEFAULT_BRANCH}"], "git merge"
        )
        if rc_box[0] != 0:
            yield {"type": "line",
                   "text": "[updater] merge не прошёл — делаю reset --hard origin/main"}
            yield from _run_step(
                ["git", "reset", "--hard", f"origin/{_DEFAULT_BRANCH}"], "git reset"
            )
            if rc_box[0] != 0:
                yield {"type": "done", "ok": False, "step": "git reset",
                       "message": f"git reset завершился с кодом {rc_box[0]}"}
                return
    else:
        bootstrap = [
            (["git", "init", "-b", _DEFAULT_BRANCH], "git init"),
            (["git", "remote", "add", "origin", _REMOTE_URL], "git remote add"),
            (["git", "fetch", "origin", _DEFAULT_BRANCH], "git fetch"),
            (["git", "reset", "--hard", f"origin/{_DEFAULT_BRANCH}"], "git reset"),
            (["git", "branch", "--set-upstream-to",
              f"origin/{_DEFAULT_BRANCH}", _DEFAULT_BRANCH], "git branch upstream"),
        ]
        for cmd, label in bootstrap:
            yield from _run_step(cmd, label)
            # set-upstream-to может упасть, если ветка уже настроена —
            # это не фатально для bootstrap-а.
            if rc_box[0] != 0 and label != "git branch upstream":
                yield {"type": "done", "ok": False, "step": label,
                       "message": f"{label} завершился с кодом {rc_box[0]}"}
                return

    # uv sync — финальный шаг.
    yield from _run_step(["uv", "sync"], "uv sync")
    if rc_box[0] != 0:
        yield {"type": "done", "ok": False, "step": "uv sync",
               "message": f"uv sync завершился с кодом {rc_box[0]}"}
        return

    yield {
        "type": "done",
        "ok": True,
        "message": "Обновление установлено. Перезапустите приложение.",
        "version": current_version(),
    }


def apply() -> dict[str, Any]:
    """Обновляет рабочее дерево до последнего коммита `main` и делает `uv sync`.

    Если `.git` отсутствует (установка из ZIP) — инициализирует репозиторий и
    делает `git fetch` + `git reset --hard origin/main`. Возвращает логи;
    пользователь должен перезапустить приложение вручную.
    """

    def _run(cmd: list[str]) -> dict[str, Any]:
        try:
            p = subprocess.run(
                cmd,
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=_STEP_TOTAL_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as e:
            return {
                "cmd": " ".join(cmd),
                "code": -1,
                "stdout": e.stdout or "",
                "stderr": (e.stderr or "") + f"\n[updater] таймаут {_STEP_TOTAL_TIMEOUT_S}s",
            }
        return {"cmd": " ".join(cmd), "code": p.returncode, "stdout": p.stdout, "stderr": p.stderr}

    log: list[dict[str, Any]] = []
    git_dir = PROJECT_ROOT / ".git"

    if git_dir.exists():
        # Используем fetch+merge вместо `git pull --ff-only`, чтобы не зависеть
        # от настроенного upstream-трекинга (после ручного `git init` его нет).
        fetch = _run(["git", "fetch", "origin", _DEFAULT_BRANCH])
        log.append(fetch)
        if fetch["code"] != 0:
            return {"ok": False, "step": "git fetch", "log": log}
        merge = _run(["git", "merge", "--ff-only", f"origin/{_DEFAULT_BRANCH}"])
        log.append(merge)
        if merge["code"] != 0:
            # Конфликт с локальными правками tracked-файлов (uv.lock и т.п.) —
            # fallback на reset --hard. Untracked-файлы reset не трогает.
            reset = _run(["git", "reset", "--hard", f"origin/{_DEFAULT_BRANCH}"])
            log.append(reset)
            if reset["code"] != 0:
                return {"ok": False, "step": "git reset", "log": log}
    else:
        # Установка из ZIP — поднимаем git-репозиторий поверх существующих файлов.
        for cmd, label in [
            (["git", "init", "-b", _DEFAULT_BRANCH], "git init"),
            (["git", "remote", "add", "origin", _REMOTE_URL], "git remote add"),
            (["git", "fetch", "origin", _DEFAULT_BRANCH], "git fetch"),
            (["git", "reset", "--hard", f"origin/{_DEFAULT_BRANCH}"], "git reset"),
            (["git", "branch", "--set-upstream-to", f"origin/{_DEFAULT_BRANCH}", _DEFAULT_BRANCH],
             "git branch upstream"),
        ]:
            step = _run(cmd)
            log.append(step)
            # `branch --set-upstream-to` может упасть, если ветка ещё не создана —
            # это не фатально, остальное уже отработало.
            if step["code"] != 0 and label != "git branch upstream":
                return {"ok": False, "step": label, "log": log}

    sync = _run(["uv", "sync"])
    log.append(sync)
    if sync["code"] != 0:
        return {"ok": False, "step": "uv sync", "log": log}

    return {
        "ok": True,
        "log": log,
        "message": "Обновление установлено. Перезапустите приложение.",
        "version": current_version(),
    }
