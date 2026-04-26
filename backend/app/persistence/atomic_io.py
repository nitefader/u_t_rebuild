"""Atomic file write helper — write to a temp file, then rename in place.

Used by every JSON-backed store in the system so a crash mid-write
cannot leave a corrupt file behind. The temp file lives next to the
target so the final rename is on the same filesystem (atomic on
POSIX, best-effort atomic on Windows via ``os.replace``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def write_text_atomic(path: Path | str, content: str, *, encoding: str = "utf-8") -> None:
    """Write ``content`` to ``path`` atomically (no torn write on crash)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding=encoding)
    os.replace(tmp, target)


def write_json_atomic(path: Path | str, payload: Any, *, indent: int = 2, sort_keys: bool = False) -> None:
    """Serialize ``payload`` to JSON and write atomically."""
    write_text_atomic(path, json.dumps(payload, indent=indent, sort_keys=sort_keys, default=str))
