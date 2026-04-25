"""Точка входа: поднимает FastAPI-сервер в фоне и запускает menu bar приложение.

Запуск:
    python run.py
или:
    MEETING_SCRIBE_NO_MENUBAR=1 python run.py   # только сервер, без иконки
"""
from __future__ import annotations

import os
import sys
import threading
import time

import uvicorn

from app.config import HOST, PORT, ensure_dirs
from app import storage


def _serve() -> None:
    uvicorn.run(
        "app.server:app",
        host=HOST,
        port=PORT,
        log_level="info",
        access_log=False,
    )


def _wait_until_up(timeout: float = 10.0) -> bool:
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout
    url = f"http://{HOST}:{PORT}/api/status"
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=0.5).read()
            return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.2)
    return False


def _open_browser_when_ready() -> None:
    if not _wait_until_up():
        print("Сервер не поднялся за 10 секунд — браузер не открываю.", file=sys.stderr)
        return
    print(f"✅ Meeting Scribe запущен на http://{HOST}:{PORT}", flush=True)
    try:
        import webbrowser
        host = "127.0.0.1" if HOST in ("0.0.0.0", "::", "") else HOST
        webbrowser.open(f"http://{host}:{PORT}")
    except Exception as e:  # noqa: BLE001
        print(f"Не удалось открыть браузер автоматически: {e}", file=sys.stderr)


def main() -> None:
    ensure_dirs()
    storage.init_db()

    try:
        from app.updater import current_version
        print(f"Транскрибатор (real-time) v{current_version()}", flush=True)
    except Exception:
        pass

    no_menubar = os.environ.get("MEETING_SCRIBE_NO_MENUBAR") == "1" or sys.platform != "darwin"

    if no_menubar:
        # Без menubar (Windows / Linux): uvicorn в главном потоке — корректный
        # graceful shutdown по Ctrl+C, без daemon-tread с обрывом SSE.
        # Браузер открываем из watcher-треда, как только сервер ответит.
        threading.Thread(target=_open_browser_when_ready, daemon=True).start()
        _serve()
        return

    # macOS: rumps/AppKit обязан жить в главном потоке, поэтому uvicorn —
    # в фоновом треде. Здесь это допустимо: menubar.run() и так блокирует
    # main thread до закрытия приложения.
    server_thread = threading.Thread(target=_serve, daemon=True)
    server_thread.start()
    if not _wait_until_up():
        print("Сервер не поднялся за 10 секунд", file=sys.stderr)
        sys.exit(1)
    print(f"✅ Meeting Scribe запущен на http://{HOST}:{PORT}", flush=True)
    from app.menubar import run as run_menubar
    run_menubar()


if __name__ == "__main__":
    main()
