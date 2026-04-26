from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from backend.app.persistence import write_json_atomic, write_text_atomic


def test_write_text_atomic_writes_via_temp_file_and_replaces(tmp_path) -> None:
    target = tmp_path / "subdir" / "out.txt"
    write_text_atomic(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"
    # No leftover .tmp file.
    assert not target.with_suffix(target.suffix + ".tmp").exists()


def test_write_json_atomic_serializes_with_indent_default(tmp_path) -> None:
    target = tmp_path / "out.json"
    write_json_atomic(target, {"b": 1, "a": 2})
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {"b": 1, "a": 2}
    # Indented for human-readability.
    assert "\n  " in target.read_text(encoding="utf-8")


def test_write_json_atomic_sort_keys_option(tmp_path) -> None:
    target = tmp_path / "out.json"
    write_json_atomic(target, {"z": 1, "a": 2}, sort_keys=True)
    raw = target.read_text(encoding="utf-8")
    assert raw.index("\"a\"") < raw.index("\"z\"")


def test_write_text_atomic_does_not_corrupt_existing_file_on_crash(tmp_path) -> None:
    """If os.replace fails, the original file content is preserved."""
    target = tmp_path / "out.txt"
    target.write_text("original", encoding="utf-8")

    with patch("backend.app.persistence.atomic_io.os.replace", side_effect=OSError("boom")):
        with pytest.raises(OSError):
            write_text_atomic(target, "new content")

    assert target.read_text(encoding="utf-8") == "original"
