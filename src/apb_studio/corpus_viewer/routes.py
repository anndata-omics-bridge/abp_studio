"""Corpus-specific HTTP reads layered over the shared static viewer routes."""

from __future__ import annotations

import json
import posixpath
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from apb_studio.corpus.catalog import build_catalog
from apb_studio.corpus.tables import read_rows, resolve_file
from apb_studio.fixture_store import Store
from apb_studio.fixture_viewer.routes import Response, headers_for, inline_file
from apb_studio.fixture_viewer.routes import resolve as resolve_static

CATALOG_PATH = "api/catalog"
SOURCE_PATH = "api/source"
INPUT_KINDS_PATH = "api/input-kinds"
_SOURCE_FIELDS = ("input_file", "vendor_parameter_file", "fasta")


def _error(status: int, message: str) -> Response:
    return Response(status, (("Content-Type", "text/plain; charset=utf-8"),), message.encode())


def _inside(root: Path, relative: str) -> Path | None:
    target = (root / relative).resolve()
    return target if target.is_relative_to(root.resolve()) else None


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _source(store: Store, query: str) -> Response:
    parameters = parse_qs(query)
    context = parameters.get("context", [""])[0]
    relative = parameters.get("path", [""])[0]
    directory = _inside(store.root, context)
    if not relative or directory is None or not directory.is_dir():
        return _error(404, "Unknown source context")

    manifest = _read_json(directory / "run.json") or {}
    settings_path = _inside(
        directory,
        str(manifest.get("execution_settings", "execution_settings.json")),
    )
    settings = _read_json(settings_path) if settings_path is not None else None
    corpus = _inside(directory, str(manifest.get("source_corpus", "corpus.csv")))
    try:
        if settings is None or corpus is None or not corpus.is_file():
            raise FileNotFoundError
        allowed = {
            row[field] for row in read_rows(corpus) for field in _SOURCE_FIELDS if row.get(field)
        }
        workflow_name = manifest.get("workflow_table")
        if isinstance(workflow_name, str) and workflow_name:
            workflow = _inside(directory, workflow_name)
            if workflow is None or not workflow.is_file():
                raise FileNotFoundError
            allowed.update(
                row[field]
                for row in read_rows(workflow)
                for field in _SOURCE_FIELDS
                if row.get(field)
            )
    except (OSError, ValueError):
        return _error(404, "Source metadata unavailable")
    if relative not in allowed:
        return _error(403, "Source path is not in the run's input snapshots")

    try:
        data_root = settings.get("data_root")
        if not isinstance(data_root, str):
            raise ValueError
        target = resolve_file(Path(data_root), relative)
    except ValueError:
        return _error(403, "Invalid source data root")
    return inline_file(target)


def _input_kinds(store: Store, query: str) -> Response:
    """Describe actual input kinds for one frozen run without reading vendor content."""
    context = parse_qs(query).get("context", [""])[0]
    directory = _inside(store.root, context)
    if not context or directory is None or not directory.is_dir():
        return _error(404, "Unknown source context")
    manifest = _read_json(directory / "run.json") or {}
    settings_path = _inside(
        directory, str(manifest.get("execution_settings", "execution_settings.json"))
    )
    settings = _read_json(settings_path) if settings_path is not None else None
    corpus = _inside(directory, str(manifest.get("corpus", "corpus.csv")))
    try:
        if settings is None or corpus is None or not corpus.is_file():
            raise FileNotFoundError
        rows = read_rows(corpus)
    except (OSError, ValueError):
        return _error(404, "Source metadata unavailable")
    data_root = settings.get("data_root")
    if not isinstance(data_root, str):
        return _error(403, "Invalid source data root")
    kinds: dict[str, str] = {}
    try:
        for row in rows:
            relative = row.get("input_file")
            if not relative:
                continue
            target = resolve_file(Path(data_root), relative)
            if target.is_file():
                kinds[relative] = "file"
            elif target.is_dir():
                kinds[relative] = "folder"
    except (OSError, ValueError):
        return _error(403, "Invalid input path")
    body = (json.dumps({"schema_version": 2, "input_kinds": kinds}) + "\n").encode()
    return Response(200, headers_for("input-kinds.json"), body)


def resolve(url_path: str, web_root: Path, store: Store) -> Response:
    """Serve the live corpus catalog, delegating every other read to static routes."""
    parsed = urlsplit(url_path)
    path = unquote(parsed.path)
    clean = posixpath.normpath(path).lstrip("/")
    if clean == CATALOG_PATH:
        body = (json.dumps(build_catalog(store.root), indent=2) + "\n").encode()
        return Response(200, headers_for("catalog.json"), body)
    if clean == SOURCE_PATH:
        return _source(store, parsed.query)
    if clean == INPUT_KINDS_PATH:
        return _input_kinds(store, parsed.query)
    return resolve_static(url_path, web_root, store)
