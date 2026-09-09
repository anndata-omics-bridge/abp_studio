"""URL to bytes, with no HTTP machinery in sight.

:func:`resolve` maps a request path onto a :class:`Response`; the handler in
:mod:`apb_studio.fixture_viewer.server` does nothing but write it, so every routing
rule, header and refusal is testable without a socket.

Two roots share one origin: the viewer is served from ``/`` and the store from
``/data/``. Those trees are plain files; a small identity route hashes their configured
roots so lifecycle commands cannot mistake one viewer for another. ``index.json`` is
written by :mod:`apb_studio.fixture_index` when a command changes the store.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import posixpath
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from apb_studio.fixture_store import INDEX_NAME, Store

DATA_PREFIX = "data"
VIEWER_IDENTITY_PATH = ".well-known/apb-studio-viewer.json"

_NO_CACHE = ("Cache-Control", "no-cache")
_HEADERS_BY_SUFFIX: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (".csv", (("Content-Type", "text/csv; charset=utf-8"), _NO_CACHE)),
    (".tsv", (("Content-Type", "text/tab-separated-values; charset=utf-8"), _NO_CACHE)),
    (".json", (("Content-Type", "application/json"), _NO_CACHE)),
    (".html", (("Content-Type", "text/html; charset=utf-8"), _NO_CACHE)),
    (".js", (("Content-Type", "text/javascript; charset=utf-8"), _NO_CACHE)),
    (".css", (("Content-Type", "text/css; charset=utf-8"), _NO_CACHE)),
    (".toml", (("Content-Type", "text/plain; charset=utf-8"), _NO_CACHE)),
    (".txt", (("Content-Type", "text/plain; charset=utf-8"), _NO_CACHE)),
    (".fasta", (("Content-Type", "text/plain; charset=utf-8"), _NO_CACHE)),
    (".parquet", (("Content-Type", "application/octet-stream"), _NO_CACHE)),
)


@dataclass(frozen=True, eq=False)
class Response:
    """One complete HTTP response, without ``Content-Length``."""

    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes


def headers_for(name: str) -> tuple[tuple[str, str], ...]:
    """Choose response headers from a file name."""
    for suffix, headers in _HEADERS_BY_SUFFIX:
        if name.endswith(suffix):
            return headers
    guessed, _ = mimetypes.guess_type(name)
    return (("Content-Type", guessed or "application/octet-stream"), _NO_CACHE)


def _error(status: int, message: str) -> Response:
    return Response(
        status, (("Content-Type", "text/plain; charset=utf-8"), _NO_CACHE), message.encode("utf-8")
    )


def _under(root: Path, relative: str) -> Path | None:
    """Resolve a relative URL path inside a root, refusing escapes."""
    candidate = (root / relative).resolve()
    return candidate if candidate.is_relative_to(root.resolve()) else None


def _file(path: Path) -> Response:
    if not path.is_file():
        return _error(404, f"Not found: {path.name}")
    return Response(200, headers_for(path.name), path.read_bytes())


def _data(store: Store, relative: str) -> Response:
    """Resolve one path below ``/data/`` onto a file in the store."""
    target = _under(store.root, relative or INDEX_NAME)
    if target is None:
        return _error(403, "Path outside the store")
    return _file(target)


def viewer_identity(web_root: Path, store: Store) -> bytes:
    """Return a stable identity for one exact viewer and store pairing."""
    payload = {
        "schema_version": 1,
        "server": "apb-studio-static-viewer",
        "store": hashlib.sha256(str(store.root.resolve()).encode()).hexdigest(),
        "viewer": hashlib.sha256(str(web_root.resolve()).encode()).hexdigest(),
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def resolve(url_path: str, web_root: Path, store: Store) -> Response:
    """Map one request path onto its complete response."""
    path = unquote(url_path.split("?", 1)[0].split("#", 1)[0])
    clean = posixpath.normpath(path).lstrip("/")
    if clean == VIEWER_IDENTITY_PATH:
        return Response(200, headers_for(VIEWER_IDENTITY_PATH), viewer_identity(web_root, store))
    if clean in {".", ""}:
        return _file(web_root / "index.html")
    head, _, tail = clean.partition("/")
    if head == DATA_PREFIX:
        return _data(store, tail)
    target = _under(web_root, clean)
    if target is None:
        return _error(403, "Path outside the web root")
    return _file(target)
