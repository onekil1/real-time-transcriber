"""Проверка и установка обновлений из GitHub Releases.

Источник истины — последний релиз в репозитории `GITHUB_REPO`.
Применение обновления = `git pull` + `uv sync` в `PROJECT_ROOT`,
после чего пользователь должен вручную перезапустить приложение.
"""
from __future__ import annotations

import re
import subprocess
from typing import Any

import requests

from .config import PROJECT_ROOT

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


def apply() -> dict[str, Any]:
    """`git pull` + `uv sync`. Возвращает логи; пользователь должен перезапустить приложение."""

    def _run(cmd: list[str]) -> dict[str, Any]:
        p = subprocess.run(
            cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=300
        )
        return {"cmd": " ".join(cmd), "code": p.returncode, "stdout": p.stdout, "stderr": p.stderr}

    pull = _run(["git", "pull", "--ff-only"])
    if pull["code"] != 0:
        return {"ok": False, "step": "git pull", "log": [pull]}

    sync = _run(["uv", "sync"])
    if sync["code"] != 0:
        return {"ok": False, "step": "uv sync", "log": [pull, sync]}

    return {
        "ok": True,
        "log": [pull, sync],
        "message": "Обновление установлено. Перезапустите приложение.",
        "version": current_version(),
    }
