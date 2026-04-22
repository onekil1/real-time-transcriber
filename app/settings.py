from __future__ import annotations

from .config import DATA_DIR, ensure_dirs

_GLOSSARY_FILE = DATA_DIR / "glossary.txt"


def get_glossary() -> str:
    try:
        return _GLOSSARY_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
    except Exception:
        return ""


def set_glossary(text: str) -> None:
    ensure_dirs()
    _GLOSSARY_FILE.write_text((text or "").strip(), encoding="utf-8")
