"""Generate a ``corpus.yaml`` by scanning a data tree — so the dashboard/pipeline can manage a real
corpus of hundreds of files without hand-authoring config.

It walks ``<data_root>/<module>/<dataset>/`` directories that hold a vendor output + a parameter
file, detects the **vendor** (reusing apb's ``recognize_software`` — no bespoke sniffing) and the
quantification **level** (from the module directory name), and writes a ``corpus.yaml`` grouped by
(module, vendor). Run it, review/edit the result (e.g. add ``annotation:`` JSON files), then point the
dashboard/Snakefile at it. The detected vendor lands *in* the config — decision 14 (declared, not
sniffed at run time); the scan only bootstraps the declaration.

    python -m apb_studio.scaffold --data <root> --output config/corpus.yaml
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import yaml

from apb_studio.pipeline import LEVELS, MULTI_LEVEL_VENDORS, SINGLE_LEVEL_VENDOR_LEVELS

# Preferred input filenames (ProteoBench cache layout), tried in order; else the largest data file.
_INPUT_CANDIDATES = (
    "input_file.parquet",
    "input_file.tsv",
    "input_file.txt",
    "input_file_secondary.tsv",
    "report.parquet",
    "report.tsv",
    "evidence.txt",
)
_PARAM_GLOBS = ("param_0.*", "param*.*", "*report.log.txt", "parameters.*", "*.log.txt")
_DATA_SUFFIXES = {".tsv", ".txt", ".parquet", ".csv"}
_SKIP_NAMES = {"comment.txt", "result_performance.csv"}


def read_headers(path: Path | str) -> list[str]:
    """Column names of a vendor file (for vendor detection). Delimited files sniff tab-vs-comma."""
    path = Path(path)
    if path.suffix == ".parquet":
        try:
            import pyarrow.parquet as pq

            return list(pq.read_schema(path).names)
        except Exception:  # noqa: BLE001 - parquet headers are best-effort
            return []
    with open(path, encoding="utf-8", errors="replace") as handle:
        line = handle.readline().rstrip("\n")
    delimiter = "\t" if line.count("\t") >= line.count(",") else ","
    return [col.strip().strip('"') for col in line.split(delimiter)]


def apb_recognizer():
    """apb's column-based vendor recognizer (slug or None). Errors clearly if apb isn't importable."""
    try:
        from anndata_proteomics.converters.pipeline import recognize_software
    except (
        ImportError
    ) as exc:  # pragma: no cover - exercised only without apb installed
        raise SystemExit(
            "scaffold needs the `apb` package importable for vendor detection — install it "
            "(uv pip install -e ../apb)"
        ) from exc
    return recognize_software


def detect_level(module_name: str) -> str | None:
    """The quantification level encoded in a module name (e.g. ``Results_quant_ion_…`` → ``ion``)."""
    tokens = module_name.lower().replace("-", "_").split("_")
    return next((lvl for lvl in LEVELS if lvl in tokens), None)


def find_input(dataset_dir: Path) -> Path | None:
    """The vendor output file in a dataset dir (preferred names, else the largest data file)."""
    for name in _INPUT_CANDIDATES:
        candidate = dataset_dir / name
        if candidate.is_file():
            return candidate
    data_files = [
        p
        for p in dataset_dir.iterdir()
        if p.is_file()
        and p.suffix in _DATA_SUFFIXES
        and p.name not in _SKIP_NAMES
        and not p.name.startswith("param")
    ]
    return max(data_files, key=lambda p: p.stat().st_size, default=None)


def find_param(dataset_dir: Path, input_path: Path) -> Path | None:
    """The co-located parameter/log file (gives the software version → ``apb convert --params``)."""
    for pattern in _PARAM_GLOBS:
        for candidate in sorted(dataset_dir.glob(pattern)):
            if candidate.is_file() and candidate != input_path:
                return candidate
    return None


def discover(data_root: Path | str):
    """Yield ``(module, dataset, input_path, param_path)`` for ``<root>/<module>/<dataset>/`` dirs
    that hold both a vendor output and a parameter file."""
    root = Path(data_root)
    for module_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for dataset_dir in sorted(p for p in module_dir.iterdir() if p.is_dir()):
            input_path = find_input(dataset_dir)
            if input_path is None:
                continue
            param_path = find_param(dataset_dir, input_path)
            if param_path is None:
                continue
            yield module_dir.name, dataset_dir.name, input_path, param_path


def build_corpus(
    data_root: Path | str,
    *,
    input_root: Path | str | None = None,
    output_root: str = "apb_outputs",
    recognizer=None,
) -> tuple[dict, list[str]]:
    """Build the corpus dict (grouped by module×vendor) and the list of skipped datasets.

    Returns ``(corpus, skipped)``. A dataset is skipped when its vendor cannot be detected.
    """
    root = Path(data_root)
    base = Path(input_root) if input_root is not None else root
    recognize = recognizer or apb_recognizer()

    # A module is the ProteoBench benchmark (shared runs); its datasets are the different tools'
    # outputs, so `vendor`/`level` live on each DATASET, not the module name.
    raw: dict[str, list[dict]] = defaultdict(list)
    skipped: list[str] = []
    for module, dataset_dir, input_path, param_path in discover(root):
        vendor = recognize(read_headers(input_path))
        if not vendor:
            skipped.append(f"{module}/{dataset_dir}")
            continue
        raw[module].append(
            {
                "vendor": vendor,
                "dir": dataset_dir,
                "input": str(input_path.relative_to(base)),
                "params": str(param_path.relative_to(base)),
            }
        )

    modules: dict[str, dict] = {}
    for module, items in sorted(raw.items()):
        level = (
            detect_level(module) or "ion"
        )  # the module's quant level, declared on single-level datasets
        datasets: list[dict] = []
        seen: set[str] = set()
        for item in sorted(items, key=lambda x: (x["vendor"], x["dir"])):
            name = f"{item['vendor']}-{item['dir'][:8]}"
            if name in seen:  # rare hash-prefix clash → fall back to the full dir name
                name = f"{item['vendor']}-{item['dir']}"
            seen.add(name)
            entry = {"name": name, "vendor": item["vendor"]}
            if (
                item["vendor"] not in MULTI_LEVEL_VENDORS
            ):  # decision 16: single-level declares level
                # The level is the VENDOR's native level (apb's rule level), not the module name's —
                # e.g. WOMBAT is peptidoform even in an "…_ion_…" module. Fall back to the module level
                # for a vendor not in the map.
                entry["level"] = SINGLE_LEVEL_VENDOR_LEVELS.get(item["vendor"], level)
            entry["input"] = item["input"]
            entry["params"] = item["params"]
            datasets.append(entry)
        modules[module] = {"datasets": datasets}

    corpus = {
        "input_root": str(base),
        "output_root": str(output_root),
        "modules": modules,
    }
    return corpus, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="apb_studio.scaffold")
    parser.add_argument(
        "--data",
        required=True,
        help="data root: <root>/<module>/<dataset>/{input,param}",
    )
    parser.add_argument(
        "--output", default="config/corpus.yaml", help="corpus.yaml to write"
    )
    parser.add_argument(
        "--input-root",
        default=None,
        help="prefix for dataset input/params (default: --data)",
    )
    parser.add_argument(
        "--output-root",
        default="apb_outputs",
        help="where the pipeline writes artifacts",
    )
    args = parser.parse_args(argv)

    corpus, skipped = build_corpus(
        args.data, input_root=args.input_root, output_root=args.output_root
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(corpus, sort_keys=False), encoding="utf-8")

    n_datasets = sum(len(m["datasets"]) for m in corpus["modules"].values())
    print(f"wrote {out}: {len(corpus['modules'])} module(s), {n_datasets} dataset(s)")
    if skipped:
        shown = ", ".join(skipped[:8]) + (" …" if len(skipped) > 8 else "")
        print(f"skipped {len(skipped)} dataset(s) with undetectable vendor: {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
