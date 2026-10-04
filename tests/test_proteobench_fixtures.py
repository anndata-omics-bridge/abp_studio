"""Behavior and failure-path coverage for the fixture-store CLI."""

from __future__ import annotations

import ast
import io
import json
import math
import os
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import requests
from bs4 import BeautifulSoup
from pydantic import ValidationError

from apb_studio import proteobench_fixtures as rawdb
from apb_studio.fixture_store import Store
from apb_studio.settings import StudioSettings


class _Response:
    def __init__(
        self,
        *,
        content: bytes = b"",
        text: str = "",
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        chunks: tuple[bytes, ...] | None = None,
        fail_after: int | None = None,
        http_error: str = "",
    ) -> None:
        self.content = content
        self.text = text
        self.status_code = status_code
        self.headers = headers if headers is not None else {"Content-Length": str(len(content))}
        self._chunks = chunks
        self._fail_after = fail_after
        self._http_error = http_error
        self.status_checked = False

    def raise_for_status(self) -> None:
        self.status_checked = True
        if self._http_error:
            raise requests.HTTPError(self._http_error, response=cast(requests.Response, self))

    def iter_content(self, _size: int) -> Iterator[bytes]:
        for index, chunk in enumerate(
            self._chunks if self._chunks is not None else (self.content,)
        ):
            if self._fail_after is not None and index >= self._fail_after:
                raise requests.ConnectionError("connection reset")
            yield chunk

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return stream.getvalue()


def _catalog_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "module": ["dda_qexactive"] * 4 + ["dia_aif"],
        "repo_name": ["Repo", "Repo", "Repo", "Repo", "Other"],
        "software_name": ["A", "A", "A", "B", "C"],
        "software_version": ["1", "1", "2", "1", "9"],
        "nr_feature": [2, 1, 3, None, 7],
        "intermediate_hash": ["b", "a", "c", "d", "e"],
    })


def test_store_defaults_to_studio_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        rawdb,
        "load_settings",
        lambda: StudioSettings(test_data_root=tmp_path, output_root=tmp_path / "out"),
    )
    assert rawdb._store(None).root == tmp_path.resolve()
    assert rawdb._store(tmp_path / "other").root == (tmp_path / "other").resolve()


def test_submission_metadata_reads_nan_text_fields_as_missing() -> None:
    document = (
        '{"intermediate_hash": "h", "software_name": "Tool", '
        '"software_version": NaN, "old_new": NaN, "nr_feature": NaN}'
    )
    metadata = rawdb._SubmissionMetadata.model_validate_json(document)
    assert metadata.software_version is None
    assert metadata.old_new is None
    assert metadata.software_name == "Tool"
    assert metadata.nr_feature is not None and math.isnan(metadata.nr_feature)
    assert rawdb._feature_count(rawdb._SubmissionMetadata(nr_feature=None, nr_prec=2)) == 2


def test_safe_zip_extraction(tmp_path: Path) -> None:
    with zipfile.ZipFile(io.BytesIO(_zip_bytes({"root/file.txt": b"x"}))) as archive:
        rawdb._extract_zip(archive, tmp_path)
    assert (tmp_path / "root/file.txt").read_text(encoding="utf-8") == "x"
    with zipfile.ZipFile(io.BytesIO(_zip_bytes({"../escape.txt": b"x"}))) as archive:
        with pytest.raises(RuntimeError, match="Unsafe ZIP member"):
            rawdb._extract_zip(archive, tmp_path)


def test_get_merged_json_discovers_redirected_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = _Response(content=_zip_bytes({"Renamed-main/a.json": b"{}"}))
    monkeypatch.setattr(rawdb.requests, "get", lambda _url, **_kwargs: response)
    monkeypatch.chdir(tmp_path)
    extracted = rawdb.get_merged_json("https://github.com/org/Original/archive/refs/heads/main.zip")
    assert extracted == Path("Original") / "Renamed-main"
    assert (tmp_path / extracted / "a.json").exists()
    assert response.status_checked
    response.content = _zip_bytes({"one/a": b"", "two/b": b""})
    with pytest.raises(RuntimeError, match="one root folder"):
        rawdb.get_merged_json("https://github.com/org/Original/archive/refs/heads/main.zip")


def test_every_request_carries_a_timeout() -> None:
    """A server that accepts and then stops sending must fail, not hang the run."""
    tree = ast.parse(Path(rawdb.__file__).read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "requests"
    ]
    assert len(calls) >= 5, "no requests to check"
    for call in calls:
        keywords = {keyword.arg for keyword in call.keywords}
        assert "timeout" in keywords, f"line {call.lineno} has no timeout"
    connect, read = rawdb.REQUEST_TIMEOUT
    assert connect > 0 and read > 0


def test_a_stalled_archive_resumes_where_it_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dead connection costs one attempt, not the bytes already on disk."""
    monkeypatch.setattr(rawdb.time, "sleep", lambda _seconds: None)
    payload = _zip_bytes({"input_file.tsv": b"a\tb\n1\t2\n"})
    half = len(payload) // 2
    calls: list[dict[str, str]] = []

    def _get(_url: str, **kwargs: Any) -> _Response:
        headers = kwargs.get("headers") or {}
        calls.append(headers)
        if not headers:
            # First attempt: sends half the archive, then the connection dies.
            return _Response(
                chunks=(payload[:half], payload[half:]),
                fail_after=1,
                headers={"Content-Length": str(len(payload))},
            )
        start_byte = int(headers["Range"].removeprefix("bytes=").rstrip("-"))
        return _Response(
            chunks=(payload[start_byte:],),
            status_code=206,
            headers={"Content-Range": f"bytes {start_byte}-{len(payload) - 1}/{len(payload)}"},
        )

    monkeypatch.setattr(rawdb.requests, "get", _get)
    destination = tmp_path / "archive.zip"

    assert rawdb.fetch_zip("https://server/archive.zip", destination) == destination

    assert destination.read_bytes() == payload
    assert calls == [{}, {"Range": f"bytes={half}-"}], "the second attempt asks for the rest"
    assert not (tmp_path / "archive.zip.part").exists()


def test_a_server_that_ignores_the_range_restarts_the_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rawdb.time, "sleep", lambda _seconds: None)
    (tmp_path / "archive.zip.part").write_bytes(b"stale prefix")
    payload = _zip_bytes({"input_file.tsv": b"x\n"})
    monkeypatch.setattr(
        rawdb.requests, "get", lambda _url, **_k: _Response(content=payload, status_code=200)
    )

    rawdb.fetch_zip("https://server/archive.zip", tmp_path / "archive.zip")

    assert (tmp_path / "archive.zip").read_bytes() == payload, "no stale prefix survives"


def test_a_download_that_never_completes_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rawdb.time, "sleep", lambda _seconds: None)
    attempts = 0

    def _get(_url: str, **_kwargs: Any) -> _Response:
        nonlocal attempts
        attempts += 1
        return _Response(chunks=(b"x",), fail_after=0)

    monkeypatch.setattr(rawdb.requests, "get", _get)
    with pytest.raises(requests.ConnectionError):
        rawdb.fetch_zip("https://server/archive.zip", tmp_path / "a.zip", attempts=3)
    assert attempts == 3, "it gives up rather than retrying forever"


def test_a_missing_url_is_not_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No amount of waiting turns a 404 into an archive."""
    monkeypatch.setattr(rawdb.time, "sleep", lambda _seconds: None)
    attempts = 0

    def _get(_url: str, **_kwargs: Any) -> _Response:
        nonlocal attempts
        attempts += 1
        return _Response(status_code=404, http_error="404 Not Found")

    monkeypatch.setattr(rawdb.requests, "get", _get)
    with pytest.raises(requests.HTTPError):
        rawdb.fetch_zip("https://server/gone.zip", tmp_path / "a.zip")
    assert attempts == 1, "a permanent failure is raised at once"


def test_bytes_that_are_not_an_archive_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A remote file replaced mid-resume splices two halves; the result is not a ZIP."""
    monkeypatch.setattr(rawdb.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        rawdb.requests, "get", lambda _url, **_k: _Response(content=b"an error page, not a zip")
    )
    with pytest.raises(OSError, match="not a ZIP archive"):
        rawdb.fetch_zip("https://server/archive.zip", tmp_path / "a.zip", attempts=2)
    assert not (tmp_path / "a.zip.part").exists(), "the bad bytes are discarded"


def test_nothing_left_to_send_accepts_only_a_complete_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rawdb.time, "sleep", lambda _seconds: None)
    payload = _zip_bytes({"input_file.tsv": b"x\n"})
    part = tmp_path / "archive.zip.part"
    part.write_bytes(payload)
    monkeypatch.setattr(
        rawdb.requests,
        "get",
        lambda _url, **_k: _Response(
            status_code=416, headers={"Content-Range": f"bytes */{len(payload)}"}
        ),
    )

    rawdb.fetch_zip("https://server/archive.zip", tmp_path / "archive.zip")
    assert (tmp_path / "archive.zip").read_bytes() == payload

    # A part longer than the remote file is not a finished download.
    part.write_bytes(payload + b"extra")
    attempts = 0

    def _get(_url: str, **_kwargs: Any) -> _Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return _Response(status_code=416, headers={"Content-Range": f"bytes */{len(payload)}"})
        return _Response(content=payload, status_code=200)

    monkeypatch.setattr(rawdb.requests, "get", _get)
    rawdb.fetch_zip("https://server/archive.zip", tmp_path / "archive.zip", attempts=3)
    assert (tmp_path / "archive.zip").read_bytes() == payload, "the oversized part was dropped"


def test_a_folder_without_a_vendor_table_is_not_a_download(tmp_path: Path) -> None:
    """A run interrupted while extracting must be retried, not counted as present."""
    repo = tmp_path / "Repo"
    complete = repo / "a"
    complete.mkdir(parents=True)
    (complete / "input_file.tsv").write_text("x\n", encoding="utf-8")
    (repo / "b").mkdir()
    partial = repo / "c"
    partial.mkdir()
    (partial / "data.zip.part").write_text("half", encoding="utf-8")

    to_download, present = rawdb.get_datasets_to_download(
        pd.DataFrame({"intermediate_hash": ["a", "b", "c"]}), repo
    )

    assert set(present) == {"a"}
    assert sorted(to_download["intermediate_hash"]) == ["b", "c"]


def test_raw_download_is_idempotent_and_leaves_no_zip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    soup = BeautifulSoup(
        '<a href="hash/">h</a><a href="archive.zip">z</a><a>none</a>', "html.parser"
    )
    assert rawdb._hrefs_ending_with(soup, "/") == ["hash/"]
    assert rawdb._hrefs_ending_with(soup, ".zip") == ["archive.zip"]

    output = tmp_path / "repo"
    present = output / "present"
    present.mkdir(parents=True)
    (present / "input_file.tsv").write_text("old", encoding="utf-8")
    half = output / "half"
    half.mkdir()
    (half / "leftover.txt").write_text("interrupted", encoding="utf-8")
    responses = {
        "https://server/": _Response(
            text='<a href="present/">p</a><a href="fresh/">f</a><a href="half/">h</a>'
        ),
        "https://server/half/": _Response(text='<a href="data.zip">d</a>'),
        "https://server/half/data.zip": _Response(
            content=_zip_bytes({"input_file.tsv": b"redone"})
        ),
        "https://server/fresh/": _Response(text='<a href="data.zip">d</a>'),
        "https://server/fresh/data.zip": _Response(content=_zip_bytes({"input_file.tsv": b"new"})),
    }
    monkeypatch.setattr(rawdb.requests, "get", lambda url, **_kwargs: responses[url])
    landed: list[str] = []
    found = rawdb.get_raw_data(
        pd.DataFrame({"intermediate_hash": ["present", "fresh", "half", "absent"]}),
        base_url="https://server/",
        output_directory=output,
        on_extracted=lambda folder: landed.append(folder),
    )
    assert landed == ["fresh", "half"], "each submission is described the moment it lands"
    assert found["present"] == present
    assert (found["fresh"] / "input_file.tsv").read_text(encoding="utf-8") == "new"
    assert (found["half"] / "input_file.tsv").read_text(encoding="utf-8") == "redone", (
        "a folder left half-extracted is fetched again, not skipped as present"
    )
    assert (present / "input_file.tsv").read_text(encoding="utf-8") == "old", "never overwritten"
    assert "absent" not in found
    assert not list(output.glob("*.zip"))


def test_metadata_refresh_replaces_restores_and_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metadata = tmp_path / "metadata"
    target = metadata / "Repo"
    target.mkdir(parents=True)
    (target / "old.json").write_text("{}", encoding="utf-8")

    def extract(repo_url: str) -> Path:
        assert repo_url
        root = Path("Repo-main")
        root.mkdir()
        (root / "new.json").write_text("{}", encoding="utf-8")
        return root

    url = "https://github.com/org/Repo/archive/refs/heads/main.zip"
    monkeypatch.setattr(rawdb, "get_merged_json", extract)
    assert rawdb._download_module_jsons(url, metadata) == target
    assert (target / "new.json").exists() and not (target / "old.json").exists()

    monkeypatch.setattr(rawdb, "get_merged_json", lambda repo_url: Path("missing"))
    with pytest.raises(RuntimeError, match="Expected extracted folder"):
        rawdb._download_module_jsons(url, metadata)

    monkeypatch.setattr(rawdb, "get_merged_json", extract)
    original_replace = Path.replace

    def fail_new_snapshot(path: Path, destination: Path) -> Path:
        if path.name == "Repo-main":
            raise OSError("replace failed")
        return original_replace(path, destination)

    monkeypatch.setattr(Path, "replace", fail_new_snapshot)
    with pytest.raises(OSError, match="replace failed"):
        rawdb._download_module_jsons(url, metadata)
    assert (target / "new.json").exists(), "the previous snapshot is restored"

    monkeypatch.setattr(Path, "replace", original_replace)
    original_is_dir = Path.is_dir
    monkeypatch.setattr(Path, "is_dir", lambda p: False if p == target else original_is_dir(p))
    with pytest.raises(RuntimeError, match="Expected extracted folder"):
        rawdb._download_module_jsons(url, metadata)


def test_strategy_flags_mark_the_smallest_per_grouping() -> None:
    flagged = rawdb._strategy_flags(_catalog_frame()).set_index("intermediate_hash")
    assert flagged["smallest_per_software_version"].to_dict() == {
        "a": True,
        "b": False,
        "c": True,
        "d": False,
        "e": True,
    }
    assert flagged["smallest_per_software"].to_dict() == {
        "a": True,
        "b": False,
        "c": False,
        "d": False,
        "e": True,
    }
    assert flagged["smallest_per_module"].to_dict() == {
        "a": True,
        "b": False,
        "c": False,
        "d": False,
        "e": True,
    }


def test_catalog_writes_rows_and_flags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = tmp_path / "metadata_source"
    metadata.mkdir()
    for name, features in (("hash-a", 5), ("hash-b", 9)):
        (metadata / f"{name}.json").write_text(
            json.dumps({"intermediate_hash": name, "software_name": "Tool", "nr_prec": features}),
            encoding="utf-8",
        )
    (metadata / "bad.json").write_text("{", encoding="utf-8")
    one_module = rawdb.CONFIG.model_copy(
        update={"modules": (rawdb.CONFIG.module("dda_qexactive"),)}
    )
    monkeypatch.setattr(rawdb, "CONFIG", one_module)
    monkeypatch.setattr(rawdb, "_download_module_jsons", lambda *_args: metadata)
    store = tmp_path / "store"
    with pytest.raises(ValidationError, match="Invalid JSON"):
        rawdb.catalog(store=store)
    (metadata / "bad.json").unlink()
    rawdb.catalog(store=store)
    catalog = pd.read_csv(Store(store).catalog_csv)
    assert catalog["intermediate_hash"].tolist() == ["hash-a", "hash-b"]
    assert catalog["repo_name"].tolist() == ["Results_quant_ion_DDA"] * 2
    assert catalog["smallest_per_module"].tolist() == [True, False]


def test_existing_dataset_detection(tmp_path: Path) -> None:
    output = tmp_path / "repo"
    (output / "present").mkdir(parents=True)
    (output / "present" / "input_file.tsv").write_text("x\n", encoding="utf-8")
    (output / "unrelated").mkdir()
    frame = pd.DataFrame({"intermediate_hash": ["present", "missing"]})
    remaining, present = rawdb.get_datasets_to_download(frame, output)
    assert remaining["intermediate_hash"].tolist() == ["missing"]
    assert present == {"present": output / "present"}
    untouched, empty = rawdb.get_datasets_to_download(frame, tmp_path / "absent")
    assert untouched is frame and empty == {}


def test_catalog_selection_rejects_unknown_or_corrupt_strategy_columns() -> None:
    catalog = _catalog_frame()
    assert rawdb._selected_catalog(catalog, None) is catalog
    with pytest.raises(ValueError, match="Unknown corpus selection strategy"):
        rawdb._selected_catalog(catalog, "smallest_by_magic")

    corrupt = catalog.assign(smallest_per_module="maybe")
    with pytest.raises(ValueError, match="has invalid values"):
        rawdb._selected_catalog(corrupt, "smallest_per_module")


def test_download_writes_manifest_statuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = Store(tmp_path)
    with pytest.raises(SystemExit, match="Run 'catalog' first"):
        rawdb.download(store=tmp_path)
    _catalog_frame().to_csv(store.catalog_csv, index=False)
    ok = store.submission_dir("Repo", "a")
    ok.mkdir(parents=True)
    (ok / "input_file.tsv").write_text("x", encoding="utf-8")
    tableless = store.submission_dir("Repo", "b")
    tableless.mkdir(parents=True)
    monkeypatch.setattr(rawdb, "get_raw_data", lambda *_args, **_kwargs: {"b": tableless})

    rawdb.download(store=tmp_path, module="dda_qexactive")

    manifest = pd.read_csv(store.downloads_csv).fillna("").set_index("intermediate_hash")
    assert manifest.loc["a", "status"] == "ok"
    assert manifest.loc["a", "input_file_path"] == "submissions/Repo/a/input_file.tsv"
    assert manifest.loc["b", "status"] == "input_file_missing", "extracted, but no table in it"
    assert manifest.loc["c", "status"] == "not_on_server"
    assert manifest.loc["e", "status"] == "not_selected", "manifest still covers the catalog"

    calls: list[Path] = []
    monkeypatch.setattr(
        rawdb,
        "get_raw_data",
        lambda _df, output_directory, **_k: calls.append(output_directory) or {},
    )
    rawdb.download(store=tmp_path)
    assert calls == [store.submissions_dir / "Other", store.submissions_dir / "Repo"]
    assert store.downloads_csv.read_text().count("input_file_path,input_file_size_bytes") == 1

    present_only = _catalog_frame().loc[lambda frame: frame["intermediate_hash"] == "a"]
    present_only.to_csv(store.catalog_csv, index=False)
    calls.clear()
    rawdb.download(store=tmp_path)
    assert calls == []

    numeric = _catalog_frame().assign(repo_name=1)
    numeric.to_csv(store.catalog_csv, index=False)
    with pytest.raises(TypeError, match="repo_name"):
        rawdb.download(store=tmp_path)

    with pytest.raises(TypeError, match="repo_name and intermediate_hash"):
        rawdb._write_downloads(store, numeric, numeric)


def test_resources_fetch_fastas_and_write_their_databases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(tmp_path)
    archive = _zip_bytes({"reference.fasta": b">P1\nAAAA\n", "__MACOSX/meta": b"x"})
    one_module = rawdb.CONFIG.model_copy(
        update={
            "modules": (rawdb.CONFIG.module("dda_qexactive"),),
            "fasta_urls": ("https://server/fasta.zip",),
        }
    )
    monkeypatch.setattr(rawdb, "CONFIG", one_module)
    requested: list[str] = []

    def get(url: str, **_kwargs: object) -> _Response:
        requested.append(url)
        return _Response(content=archive)

    monkeypatch.setattr(rawdb.requests, "get", get)
    rawdb.resources(store=tmp_path)
    assert requested == ["https://server/fasta.zip"], "module definitions are not fetched"
    assert (store.fasta_dir / "reference.fasta").exists()
    database = pq.read_table(store.fasta_dir / "reference.parquet", columns=["id", "sequence"])
    assert database.to_pylist() == [{"id": "P1", "sequence": "AAAA"}], "parsed by protein-fasta"
    assert not (store.fasta_dir / "__MACOSX").exists()
    assert not (tmp_path / "modules").exists()


def test_summarize_table_reads_delimited_and_parquet(tmp_path: Path) -> None:
    tsv = tmp_path / "input_file.tsv"
    tsv.write_text("a\tb\tc\n1\t2\t3\n4\t5\t6\n", encoding="utf-8")
    assert rawdb.summarize_table(tsv) == {
        "format": "delimited",
        "delimiter": "tab",
        "size_bytes": tsv.stat().st_size,
        "rows": 2,
        "columns": 3,
        "column_names": "a|b|c",
    }
    comma = tmp_path / "input_file.txt"
    comma.write_text("x,y\n1,2\n", encoding="utf-8")
    assert rawdb.summarize_table(comma)["delimiter"] == "comma"
    single = tmp_path / "one.tsv"
    single.write_text("only\n1\n", encoding="utf-8")
    assert rawdb.summarize_table(single)["column_names"] == "only"
    empty = tmp_path / "empty.tsv"
    empty.write_text("", encoding="utf-8")
    assert rawdb.summarize_table(empty)["columns"] == 0
    parquet = tmp_path / "input_file.parquet"
    pq.write_table(pa.table({"p": [1, 2, 3], "q": ["a", "b", "c"]}), parquet)
    summary = rawdb.summarize_table(parquet)
    assert (summary["format"], summary["rows"], summary["column_names"]) == ("parquet", 3, "p|q")


def test_a_summary_is_written_beside_each_submission(tmp_path: Path) -> None:
    store = Store(tmp_path)
    ok = store.submission_dir("Repo", "a")
    ok.mkdir(parents=True)
    (ok / "input_file.tsv").write_text("a\tb\n1\t2\n", encoding="utf-8")
    (ok / "param_0..txt").write_text("params", encoding="utf-8")

    written = rawdb.write_submission_summary(store, "Repo", "a")
    assert written is not None

    assert written == store.submission_summary("Repo", "a")
    document = json.loads(written.read_text(encoding="utf-8"))
    assert document["intermediate_hash"] == "a"
    assert document["input_file"] == "submissions/Repo/a/input_file.tsv"
    assert document["rows"] == 1
    assert document["columns"] == 2
    assert document["parameter_file"] == "submissions/Repo/a/param_0..txt"
    assert document["parameter_size_bytes"] == 6

    # The table's own mtime, so re-summarising an old download does not redate it.
    table = ok / "input_file.tsv"
    os.utime(table, (1_760_000_000, 1_760_000_000))
    redone = rawdb.write_submission_summary(store, "Repo", "a")
    assert redone is not None
    assert json.loads(redone.read_text(encoding="utf-8"))["downloaded_at"] == (
        datetime.fromtimestamp(1_760_000_000, UTC).isoformat(timespec="seconds")
    )

    empty = store.submission_dir("Repo", "b")
    empty.mkdir(parents=True)
    assert rawdb.write_submission_summary(store, "Repo", "b") is None, "no table, no summary"
    assert not store.submission_summary("Repo", "b").exists()


def test_resource_summary_covers_every_module(tmp_path: Path) -> None:
    store = Store(tmp_path)

    rawdb._write_resource_summary(store)

    resources = pd.read_csv(store.resources_csv).set_index("module")
    assert len(resources) == len(rawdb.CONFIG.modules)
    assert list(resources.columns) == ["fasta", "fasta_present"]
    assert bool(resources.loc["dda_qexactive", "fasta_present"]) is False
    assert str(resources.loc["dia_singlecell", "fasta"]).endswith("noecoli.fasta")


def test_corpus_commands_expose_all_selection_strategies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str | None, ...]] = []
    monkeypatch.setattr(
        rawdb,
        "_acquire_corpus",
        lambda *arguments: calls.append(arguments),
    )

    commands = {
        "all": (None, "all.csv"),
        "entrapment": (None, "entrapment.csv", "entrapment"),
        "plasma": (None, "plasma.csv", "plasma"),
        "smallest-per-module": ("smallest_per_module", "routine.csv"),
        "smallest-per-software": ("smallest_per_software", "routine.csv"),
        "smallest-per-software-version": ("smallest_per_software_version", "routine.csv"),
    }
    for command in commands:
        rawdb.app(["corpus", command], exit_on_error=False, result_action="return_value")

    assert calls == list(commands.values())


def test_acquire_corpus_materializes_the_selected_strategy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store(tmp_path / "test_data_download")
    catalog_frame = rawdb._strategy_flags(_catalog_frame())
    store.root.mkdir()
    catalog_frame.to_csv(store.catalog_csv, index=False)
    for row in catalog_frame.to_dict(orient="records"):
        folder = store.submission_dir(row["repo_name"], row["intermediate_hash"])
        folder.mkdir(parents=True)
        (folder / "input_file.tsv").write_text("value\n", encoding="utf-8")
        (folder / "param_0.txt").write_text("params", encoding="utf-8")

    selected_hashes: list[str] = []

    def download_selected(
        _target: Store,
        selected: pd.DataFrame,
        _catalog: pd.DataFrame,
    ) -> None:
        selected_hashes.extend(selected["intermediate_hash"].tolist())

    def write_resources(_store: Path | None = None, **_kwargs: object) -> None:
        pd.DataFrame([
            {
                "module": "dda_qexactive",
                "fasta": "fasta/reference.fasta",
            }
        ]).to_csv(store.resources_csv, index=False)

    monkeypatch.setattr(rawdb, "_store", lambda _root: store)
    monkeypatch.setattr(rawdb, "catalog", lambda **_kwargs: None)
    monkeypatch.setattr(rawdb, "_download", download_selected)
    monkeypatch.setattr(rawdb, "resources", write_resources)
    monkeypatch.setattr(rawdb.fixture_index, "write", lambda _store: None)
    workflow_table = tmp_path / "workflow_tables" / "workflow_proteobench.csv"
    workflow_table.parent.mkdir()
    workflow_table.write_text("module,fasta,level\ndda_qexactive,fasta/a.fasta,ion\n")

    rawdb._acquire_corpus("smallest_per_module", "routine.csv")

    assert workflow_table.read_text() == "module,fasta,level\ndda_qexactive,fasta/a.fasta,ion\n"
    assert [path.name for path in workflow_table.parent.iterdir()] == [workflow_table.name]
    assert selected_hashes == ["a", "e"]
    written = pd.read_csv(tmp_path / "corpuses" / "routine.csv")
    assert written["software_name"].tolist() == ["A", "C"]
    assert json.loads((tmp_path / "corpuses.json").read_text(encoding="utf-8")) == {
        "all": "corpuses/all.csv",
        "entrapment": "corpuses/entrapment.csv",
        "plasma": "corpuses/plasma.csv",
        "proteobench": "corpuses/proteobench.csv",
        "routine": "corpuses/routine.csv",
    }


def test_view_and_main_delegate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    served: list[Any] = []
    monkeypatch.setattr(
        rawdb, "serve_store", lambda store, host, port: served.append((store, host, port))
    )
    rawdb.view(store=tmp_path, host="0.0.0.0", port=1)
    assert served == [(Store(tmp_path.resolve()), "0.0.0.0", 1)]

    called: list[str] = []
    monkeypatch.setattr(rawdb, "_configure_logging", lambda: called.append("logging"))
    monkeypatch.setattr(rawdb, "app", lambda: called.append("app"))
    rawdb.main()
    assert called == ["logging", "app"]


def test_clean_empties_the_store(tmp_path: Path) -> None:
    store = Store(tmp_path)
    store.catalog_csv.write_text("module\n", encoding="utf-8")
    store.resources_csv.write_text("module\n", encoding="utf-8")
    store.index_json.write_text("{}", encoding="utf-8")
    store.submission_dir("Repo", "a").mkdir(parents=True)
    store.fasta_dir.mkdir()
    legacy = store.root / "raw_file_db_full.csv"
    legacy.write_text("old layout", encoding="utf-8")

    rawdb.clean(store=tmp_path, tables_only=True)
    assert not store.catalog_csv.exists() and not store.index_json.exists()
    assert store.submissions_dir.is_dir(), "downloads survive a tables-only clean"
    assert legacy.is_file(), "a tables-only clean touches nothing else"

    rawdb.clean(store=tmp_path)
    assert list(store.root.iterdir()) == [], "a store is re-downloadable, so nothing is kept"
    assert store.root.is_dir()

    with pytest.raises(SystemExit, match="No store to clean"):
        rawdb.clean(store=tmp_path / "absent")
    with pytest.raises(ValueError, match="Refusing to clean"):
        rawdb.clean(store=Path.home())
