from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

import rumps

from .config import BASE_URL


class ScribeApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("🎙 Scribe", quit_button=None)
        self.menu = [
            rumps.MenuItem("Начать запись", callback=self.on_start),
            rumps.MenuItem("Остановить запись", callback=self.on_stop),
            None,
            rumps.MenuItem("Загрузить файл…", callback=self.on_upload),
            rumps.MenuItem("Открыть интерфейс", callback=self.on_open),
            None,
            rumps.MenuItem("Выход", callback=self.on_quit),
        ]
        self._tick_thread: threading.Thread | None = None
        self._running = True
        self._start_tick()

    # --- helpers -----------------------------------------------------

    def _api(self, method: str, path: str, **kwargs):
        import requests  # локальный импорт — requests нужен только здесь

        return requests.request(method, f"{BASE_URL}{path}", timeout=10, **kwargs)

    def _notify(self, text: str) -> None:
        rumps.notification(title="Meeting Scribe", subtitle="", message=text)

    # --- callbacks ---------------------------------------------------

    def on_start(self, _):
        try:
            r = self._api("POST", "/api/sessions/start", json={"title": "Совещание"})
            if r.status_code == 200:
                self.title = "🔴 REC 00:00"
                self._notify("Запись началась")
            else:
                self._notify(f"Не удалось начать запись: {r.text}")
        except Exception as e:  # noqa: BLE001
            self._notify(f"Ошибка: {e}")

    def on_stop(self, _):
        try:
            s = self._api("GET", "/api/status").json()
            sid = s.get("session_id")
            if not sid:
                self._notify("Запись не идёт")
                return
            r = self._api("POST", f"/api/sessions/{sid}/stop")
            if r.status_code == 200:
                self.title = "⏳ Scribe"
                self._notify("Запись остановлена. Идёт транскрибация…")
            else:
                self._notify(f"Ошибка: {r.text}")
        except Exception as e:  # noqa: BLE001
            self._notify(f"Ошибка: {e}")

    def on_upload(self, _):
        path = _ask_file()
        if not path:
            return
        try:
            import requests

            with open(path, "rb") as f:
                r = requests.post(
                    f"{BASE_URL}/api/upload",
                    files={"file": (Path(path).name, f)},
                    data={"title": Path(path).stem},
                    timeout=60,
                )
            if r.status_code == 200:
                self._notify("Файл загружен. Обработка запущена.")
                subprocess.Popen(["open", BASE_URL])
            else:
                self._notify(f"Ошибка загрузки: {r.text}")
        except Exception as e:  # noqa: BLE001
            self._notify(f"Ошибка: {e}")

    def on_open(self, _):
        subprocess.Popen(["open", BASE_URL])

    def on_quit(self, _):
        self._running = False
        rumps.quit_application()

    # --- tick: обновляем заголовок во время записи --------------------

    def _start_tick(self) -> None:
        def loop():
            while self._running:
                try:
                    s = self._api("GET", "/api/status").json()
                    if s.get("recording"):
                        sec = int(s.get("elapsed_sec") or 0)
                        self.title = f"🔴 REC {sec // 60:02d}:{sec % 60:02d}"
                    else:
                        if self.title != "🎙 Scribe":
                            self.title = "🎙 Scribe"
                except Exception:
                    pass
                time.sleep(1.0)

        t = threading.Thread(target=loop, daemon=True)
        t.start()
        self._tick_thread = t


def _ask_file() -> str | None:
    """Показать NSOpenPanel и вернуть путь к выбранному файлу."""
    try:
        from AppKit import NSURL, NSOpenPanel  # type: ignore
    except Exception:
        # fallback: AppleScript через osascript
        try:
            r = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'POSIX path of (choose file with prompt "Выберите аудио/видео файл")',
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            path = r.stdout.strip()
            return path or None
        except subprocess.CalledProcessError:
            return None

    panel = NSOpenPanel.openPanel()
    panel.setCanChooseFiles_(True)
    panel.setCanChooseDirectories_(False)
    panel.setAllowsMultipleSelection_(False)
    panel.setAllowedFileTypes_(
        ["wav", "mp3", "m4a", "mp4", "mov", "aac", "flac", "ogg", "webm"]
    )
    if panel.runModal() != 1:  # NSModalResponseOK
        return None
    urls = panel.URLs()
    if not urls:
        return None
    return str(NSURL.fileURLWithPath_(urls[0].path()).path())


def run() -> None:
    ScribeApp().run()
