"""Pin frontend numeric constants and supported extensions to the backend
single source of truth (I7).

The FE inlines mirrors of these values in ``folder-walk.ts``. Without this
test, adding a new extension to ``_PLAIN_TEXT_EXTENSIONS`` server-side
silently makes the FE pre-flight skip files the backend would accept (or
the reverse). Same goes for the size and count caps.

If you add or change a constant on either side, update the other and this
test together.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ananta.explorers.document.config import (
    MAX_AGGREGATE_UPLOAD_BYTES,
    MAX_FOLDER_FILES,
    MAX_UPLOAD_BYTES,
    SOFT_WARN_FOLDER_FILES,
    TARGET_BATCH_BYTES,
)
from ananta.explorers.document.extractors import (
    _PLAIN_TEXT_EXTENSIONS,
    _SUPPORTED_EXTENSIONS,
)

_FOLDER_WALK_TS = (
    Path(__file__).parent.parent.parent.parent.parent
    / "src/ananta/explorers/document/frontend/src/lib/folder-walk.ts"
)


def _read_ts() -> str:
    assert _FOLDER_WALK_TS.exists(), f"folder-walk.ts not found at {_FOLDER_WALK_TS}"
    return _FOLDER_WALK_TS.read_text()


def _ts_const_int(source: str, name: str) -> int:
    """Extract ``export const NAME = <expr>`` and eval it as a Python int.

    The FE writes things like ``50 * 1024 * 1024``; we restrict eval to a
    digit/operator subset so this can't be turned into a code-execution
    surface even by a hostile change.
    """
    match = re.search(rf"export const {name} = ([0-9 *+\-]+)\b", source)
    if match is None:
        msg = f"const {name} not found in folder-walk.ts"
        raise AssertionError(msg)
    expr = match.group(1).strip()
    if not re.fullmatch(r"[0-9 *+\-]+", expr):
        msg = f"unsafe expression for {name}: {expr!r}"
        raise AssertionError(msg)
    # eval is gated by the regex above; no builtins, no globals.
    return int(eval(expr, {"__builtins__": {}}, {}))  # noqa: S307


def _ts_const_str_array(source: str, name: str) -> list[str]:
    match = re.search(
        rf"export const {name}: readonly string\[\] = \[(.+?)\]\s*as const",
        source,
        re.DOTALL,
    )
    if match is None:
        msg = f"const {name} not found in folder-walk.ts"
        raise AssertionError(msg)
    body = match.group(1)
    return [m.group(1) for m in re.finditer(r"'([^']+)'", body)]


@pytest.mark.parametrize(
    ("ts_name", "py_value"),
    [
        ("MAX_UPLOAD_BYTES", MAX_UPLOAD_BYTES),
        ("MAX_AGGREGATE_UPLOAD_BYTES", MAX_AGGREGATE_UPLOAD_BYTES),
        ("MAX_FOLDER_FILES", MAX_FOLDER_FILES),
        ("SOFT_WARN_FOLDER_FILES", SOFT_WARN_FOLDER_FILES),
        ("TARGET_BATCH_BYTES", TARGET_BATCH_BYTES),
    ],
)
def test_frontend_numeric_constants_mirror_backend(ts_name: str, py_value: int) -> None:
    """FE constants in folder-walk.ts must equal config.py."""
    assert _ts_const_int(_read_ts(), ts_name) == py_value


def test_frontend_supported_extensions_mirror_backend() -> None:
    """SUPPORTED_EXTENSIONS in folder-walk.ts must equal extractors.py.

    The backend's ``_SUPPORTED_EXTENSIONS = _PLAIN_TEXT_EXTENSIONS | {…}``
    is the source of truth — anything the BE would accept must also pass
    the FE pre-flight, or the user sees files silently skipped pre-upload
    that would have ingested fine.
    """
    ts_exts = set(_ts_const_str_array(_read_ts(), "SUPPORTED_EXTENSIONS"))
    assert ts_exts == set(_SUPPORTED_EXTENSIONS), (
        f"FE extensions diverged from BE.\n"
        f"  in FE only:  {sorted(ts_exts - set(_SUPPORTED_EXTENSIONS))}\n"
        f"  in BE only:  {sorted(set(_SUPPORTED_EXTENSIONS) - ts_exts)}"
    )


def test_plain_text_extensions_subset_of_supported() -> None:
    """Sanity check the BE structure the mirror test relies on."""
    assert _PLAIN_TEXT_EXTENSIONS <= _SUPPORTED_EXTENSIONS
