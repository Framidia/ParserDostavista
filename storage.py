from __future__ import annotations

import os
from pathlib import Path
import tempfile


def load_session(path: str) -> str | None:
    file_path = Path(path)
    if not file_path.exists():
        return None
    content = file_path.read_text(encoding="utf-8").strip()
    return content or None


def save_session(path: str, session: str) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        encoding="utf-8",
        dir=str(file_path.parent),
    ) as tmp:
        tmp.write(session.strip())
        tmp_path = tmp.name

    os.replace(tmp_path, file_path)
