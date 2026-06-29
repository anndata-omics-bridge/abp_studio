"""Run an APB conversion by shelling out to the ``apb convert`` CLI (the CLI-consumer seam).

apb_studio does not convert in-process; it launches ``apb convert`` as a background subprocess
(via ``apb_studio.conversion.runner``) so heavy fragment/MuData runs stay out of the marimo event
loop. A ``command.json`` sidecar records what was run so the converted-runs table can describe it
without re-parsing the CLI argv.
"""

from __future__ import annotations

import json
from pathlib import Path

from anndata_proteomics.converters.pipeline import MUDATA


def result_filename(target: str) -> str:
    """``result.h5mu`` for the MuData target, ``result.h5ad`` for a single level."""
    return "result.h5mu" if target == MUDATA else "result.h5ad"


def build_convert_argv(
    data_path: Path | str,
    target: str,
    *,
    params: Path | str,
    slug: str,
    output: Path | str,
) -> list[str]:
    """The ``apb convert`` argv for one conversion (real CLI form: positional data + level).

    No level token is passed for the MuData target; ``--software`` pins the vendor and
    ``--output`` fixes the result path.
    """
    argv = ["apb", "convert", str(data_path)]
    if target != MUDATA:
        argv.append(target)  # positional quantification level
    argv += ["--params", str(params), "--software", slug, "--output", str(output)]
    return argv


def start_conversion(
    data_path: Path | str,
    *,
    slug: str,
    target: str,
    params: Path | str,
    outdir: Path | str,
    runner,
    input_rel: str = "",
    run_key: str | None = None,
):
    """Launch ``apb convert`` as a background job writing into ``outdir``; return the runner Job.

    ``runner`` is ``apb_studio.conversion.runner`` (passed in to keep this import-light).
    ``input_rel`` is the catalog-relative input path, recorded in ``command.json`` for the
    converted-runs table.
    """
    outdir = Path(outdir).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)
    output = outdir / result_filename(target)
    argv = build_convert_argv(data_path, target, params=params, slug=slug, output=output)
    (outdir / "command.json").write_text(
        json.dumps(
            {
                "input_file_path": input_rel,
                "slug": slug,
                "target": target,
                "param_path": str(params),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return runner.start_job(argv, outdir, log_file=outdir / "console.log", run_key=run_key)
