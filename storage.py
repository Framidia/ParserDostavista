from __future__ import annotations

from pathlib import Path


def load_session(path: str) -> str | None:
    file_path = Path(path)
    if not file_path.exists():
        return None
    content = file_path.read_text(encoding="utf-8").strip()
    return content or None


def save_session(path: str, session: str) -> None:
    file_path = Path(path)
    file_path.write_text(session.strip(), encoding="utf-8")