"""Corpus viewer reads: the shared static routes plus the fixture store under ``/fixtures/``.

Every file the viewer reads is a file on disk, so a plain file server serves the same layout:
the viewer at ``/``, runs at ``/data/`` and the fixture store at ``/fixtures/``.
"""

from __future__ import annotations

import posixpath
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from apb_studio.fixture_store import Store
from apb_studio.fixture_viewer.routes import Response, serve_tree
from apb_studio.fixture_viewer.routes import resolve as resolve_static

FIXTURES_PREFIX = "fixtures"


def corpus_resolver(fixtures: Path) -> Callable[[str, Path, Store], Response]:
    """Serve the fixture store at ``/fixtures/`` beside the static viewer and run routes."""

    def resolve(url_path: str, web_root: Path, store: Store) -> Response:
        parsed = urlsplit(url_path)
        clean = posixpath.normpath(unquote(parsed.path)).lstrip("/")
        head, _, tail = clean.partition("/")
        if head == FIXTURES_PREFIX:
            view = parse_qs(parsed.query).get("view") == ["1"]
            return serve_tree(fixtures, tail, prefix=FIXTURES_PREFIX, view=view)
        return resolve_static(url_path, web_root, store)

    return resolve
