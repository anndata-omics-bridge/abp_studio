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

import codecs
import hashlib
import html
import json
import mimetypes
import posixpath
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from apb_studio.fixture_store import INDEX_NAME, Store

DATA_PREFIX = "data"
ASSET_PREFIX = "assets"
VIEWER_IDENTITY_PATH = ".well-known/apb-studio-viewer.json"

_NO_CACHE = ("Cache-Control", "no-store, max-age=0")
_BINARY_SUFFIXES = {
    ".h5mu",
    ".h5ad",
    ".h5",
    ".hdf5",
    ".duckdb",
    ".parquet",
    ".arrow",
    ".feather",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".bin",
    ".zip",
    ".gz",
    ".bz2",
    ".xz",
    ".7z",
    ".xls",
    ".xlsx",
}
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
    """One HTTP response backed by bytes or a file streamed by the server."""

    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes = b""
    file: Path | None = None


def headers_for(name: str) -> tuple[tuple[str, str], ...]:
    """Choose response headers from a file name."""
    for suffix, headers in _HEADERS_BY_SUFFIX:
        if name.lower().endswith(suffix):
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
    return Response(200, headers_for(path.name), file=path)


def _page(title: str, content: str) -> Response:
    body = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title>"
        "<style>body{font:16px system-ui;margin:2rem;line-height:1.5}"
        "a{color:#24588d}li{margin:.4rem 0}</style>"
        f"<h1>{html.escape(title)}</h1>{content}</html>"
    ).encode()
    return Response(200, headers_for("listing.html"), body)


def inline_file(path: Path) -> Response:
    """Stream browser-readable files unchanged; download other binary content."""
    if not path.is_file():
        return _error(404, f"Not found: {path.name}")
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _file(path)
    content_type = dict(headers_for(path.name))["Content-Type"]
    native = {".html", ".htm", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".pdf"}
    disposition = "inline"
    if suffix not in native:
        with path.open("rb") as stream:
            sample = stream.read(8192)
        try:
            codecs.getincrementaldecoder("utf-8")().decode(sample, final=False)
            text = suffix not in _BINARY_SUFFIXES and b"\0" not in sample
        except UnicodeDecodeError:
            text = False
        if not text:
            disposition = "attachment"
            content_type = "application/octet-stream"
        else:
            content_type = "text/plain; charset=utf-8"
    headers = (
        ("Content-Type", content_type),
        _NO_CACHE,
        ("Content-Disposition", f"{disposition}; filename*=UTF-8''{quote(path.name)}"),
        ("X-Content-Type-Options", "nosniff"),
    )
    return Response(200, headers, file=path)


def _directory(path: Path, root: Path) -> Response:
    entries: list[str] = []
    for child in sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold())):
        if not child.resolve().is_relative_to(root.resolve()):
            continue
        label = child.name + ("/" if child.is_dir() else "")
        href = f"/data/{quote(child.relative_to(root).as_posix())}"
        attributes = 'target="_blank" rel="noopener noreferrer"'
        if child.is_file():
            headers = dict(inline_file(child).headers)
            if headers.get("Content-Disposition", "").startswith("attachment;"):
                attributes = f'download="{html.escape(child.name, quote=True)}"'
            if child.suffix.lower() != ".json":
                href += "?view=1"
        entries.append(
            f'<li><a href="{html.escape(href, quote=True)}" {attributes}>'
            f"{html.escape(label)}</a></li>"
        )
    return _page(path.name + "/", "<ul>" + "".join(entries) + "</ul>")


def _data(store: Store, relative: str, *, view: bool) -> Response:
    """Resolve one path below ``/data/`` onto a file in the store."""
    target = _under(store.root, relative or ("." if view else INDEX_NAME))
    if target is None:
        return _error(403, "Path outside the store")
    if target.is_dir():
        return _directory(target, store.root.resolve())
    return inline_file(target) if view else _file(target)


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
    parsed = urlsplit(url_path)
    path = unquote(parsed.path)
    clean = posixpath.normpath(path).lstrip("/")
    if clean == VIEWER_IDENTITY_PATH:
        return Response(200, headers_for(VIEWER_IDENTITY_PATH), viewer_identity(web_root, store))
    if clean in {".", ""}:
        return _file(web_root / "index.html")
    head, _, tail = clean.partition("/")
    if head == DATA_PREFIX:
        return _data(store, tail, view=parse_qs(parsed.query).get("view") == ["1"])
    if head == ASSET_PREFIX:
        _release, separator, asset = tail.partition("/")
        if not separator or not asset:
            return _error(404, "Missing versioned asset")
        clean = asset
    target = _under(web_root, clean)
    if target is None:
        return _error(403, "Path outside the web root")
    return _file(target)
