"""Compact, live corpus progress dashboard for APB Studio."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import dash_ag_grid as dag
from anndata_proteomics.readers.summary import describe_path
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update

from apb_studio import execution, jobrunner, pipeline, settings
from apb_studio.registry import load_registry

_POLL_INTERVAL_MS = 1_000
_ROW_ID_FIELDS = ("module", "dataset", "level")
_STAGE_CELL_STYLE = {
    "styleConditions": [
        {
            "condition": "params.value === 'FAILED'",
            "style": {
                "backgroundColor": "#fff1f2",
                "color": "#b42318",
                "cursor": "pointer",
                "fontWeight": "600",
            },
        },
        {
            "condition": "params.value === 'UNSUPPORTED'",
            "style": {
                "backgroundColor": "#f8fafc",
                "color": "#475467",
                "cursor": "pointer",
                "fontWeight": "600",
            },
        },
        {
            "condition": "params.value === 'BLOCKED'",
            "style": {
                "backgroundColor": "#fffaeb",
                "color": "#93370d",
                "cursor": "pointer",
                "fontWeight": "600",
            },
        },
        {
            "condition": "params.value === 'DONE'",
            "style": {
                "color": "#175cd3",
                "cursor": "pointer",
                "fontWeight": "600",
                "textDecoration": "underline",
            },
        },
    ],
    "defaultStyle": {"color": "#98a2b3"},
}
_PANEL_STYLE = {
    "border": "1px solid #d0d5dd",
    "borderRadius": "6px",
    "padding": "0.75rem",
    "marginTop": "0.75rem",
}
_PRE_STYLE = {
    "backgroundColor": "#f8fafc",
    "border": "1px solid #eaecf0",
    "borderRadius": "4px",
    "fontFamily": "ui-monospace, SFMono-Regular, Menlo, monospace",
    "fontSize": "0.78rem",
    "lineHeight": "1.35",
    "margin": "0.5rem 0 0",
    "maxHeight": "360px",
    "overflow": "auto",
    "padding": "0.65rem",
    "whiteSpace": "pre-wrap",
}


def _stage_label(stage: dict[str, Any]) -> str:
    """Return a readable column label from the registry basket label."""
    label = pipeline.basket_label(stage)
    if label.lower().startswith("fasta"):
        return "FASTA" + label[5:]
    return label[:1].upper() + label[1:]


def _column_definitions(registry: list[dict]) -> list[dict[str, Any]]:
    """Build the compact branch-grid columns from the stage registry."""
    identity_columns = [
        {"field": "module", "headerName": "Module", "minWidth": 180, "flex": 1.35},
        {"field": "dataset", "headerName": "Dataset", "minWidth": 180, "flex": 1.25},
        {"field": "software", "headerName": "Software", "minWidth": 105, "flex": 0.75},
        {"field": "level", "headerName": "Level", "minWidth": 105, "flex": 0.7},
    ]
    stage_columns = [
        {
            "field": stage["name"],
            "headerName": _stage_label(stage),
            "minWidth": 125,
            "flex": 0.8,
            "cellStyle": _STAGE_CELL_STYLE,
            "filter": False,
            "sortable": False,
        }
        for stage in registry
    ]
    return [*identity_columns, *stage_columns]


def _load_dashboard_rows(
    job_id: str | None = None,
    *,
    settings_path: Path | None = None,
) -> tuple[list[dict], pipeline.RunSnapshot | None, str | None]:
    """Load authoritative branch rows and keep all UI-facing errors readable."""
    targets, _coverage, snapshot, error = execution.load_overview(
        job_id,
        settings_path=settings_path,
    )
    if error is not None:
        return [], snapshot, error
    try:
        if snapshot is None:
            return [], None, "Corpus Runner could not resolve the fixture inventory."
        rows = pipeline.branch_rows(snapshot, targets)
        return [dict(row, _row_id=_row_id(row)) for row in rows], snapshot, None
    except Exception as exc:  # noqa: BLE001 - callback boundary must remain user-facing
        return (
            [],
            snapshot,
            f"Could not build the corpus progress table: {type(exc).__name__}: {exc}",
        )


def _row_id(row: dict[str, Any]) -> str:
    """Return a stable, collision-free grid row identifier."""
    return json.dumps(
        [row.get(field) for field in _ROW_ID_FIELDS],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _selection_from_click(
    cell: dict[str, Any] | None,
    registry: list[dict],
    rows: list[dict],
) -> dict[str, str] | None:
    """Resolve AG Grid's documented row ID against authoritative server rows."""
    if not cell:
        return None
    stage_names = {stage["name"] for stage in registry}
    stage = cell.get("colId")
    if stage not in stage_names:
        return None
    clicked_row_id = cell.get("rowId")
    if not isinstance(clicked_row_id, (str, int)):
        return None
    row_id = str(clicked_row_id)
    row = next((item for item in rows if item.get("_row_id") == row_id), None)
    if row is None:
        return None
    identity = {key: row.get(key) for key in ("module", "dataset", "level")}
    if not all(isinstance(value, str) and value for value in identity.values()):
        return None
    return {**identity, "row_id": row_id, "stage": stage}


def _find_stage_detail(
    rows: list[dict],
    selection: dict[str, str] | None,
) -> dict[str, str] | None:
    """Resolve a selected stage against freshly built, authoritative rows."""
    if not selection:
        return None
    stage = selection.get("stage")
    row_id = selection.get("row_id")
    if not stage or not row_id:
        return None
    for row in rows:
        identity_matches = all(
            row.get(key) == selection.get(key) for key in _ROW_ID_FIELDS
        )
        if row.get("_row_id") == row_id and identity_matches:
            details = row.get("_stage_details", {})
            detail = details.get(stage)
            return detail if isinstance(detail, dict) else None
    return None


def _stage_heading(selection: dict[str, str], registry: list[dict]) -> str:
    """Return the branch/stage detail heading."""
    labels = {stage["name"]: _stage_label(stage) for stage in registry}
    return (
        f"{selection['module']} / {selection['dataset']} / {selection['level']}"
        f" — {labels.get(selection['stage'], selection['stage'])}"
    )


def _artifact_detail(
    detail: dict[str, str],
    selection: dict[str, str],
    registry: list[dict],
) -> list[Any]:
    """Render one completed artifact's APB-owned descriptive summary."""
    artifact = Path(detail["artifact"])
    heading = _stage_heading(selection, registry)
    try:
        summary = describe_path(artifact)
        rendered = json.dumps(summary, indent=2, sort_keys=True)
    except Exception as exc:  # noqa: BLE001 - a corrupt artifact must not crash Dash
        return [
            html.H2(heading, style={"fontSize": "1rem", "margin": "0"}),
            html.Div(str(artifact), style={"color": "#667085", "fontSize": "0.78rem"}),
            html.P(
                f"Could not read this artifact summary: {type(exc).__name__}: {exc}",
                style={"color": "#b42318"},
            ),
        ]
    return [
        html.H2(heading, style={"fontSize": "1rem", "margin": "0"}),
        html.Div(str(artifact), style={"color": "#667085", "fontSize": "0.78rem"}),
        html.Pre(rendered, style=_PRE_STYLE),
    ]


def _status_detail(
    detail: dict[str, str],
    selection: dict[str, str],
    registry: list[dict],
) -> list[Any]:
    """Render one failed, unsupported, or blocked stage diagnostic."""
    state = detail.get("state", "blocked")
    label = {
        "blocked": "BLOCKED",
        "failed": "FAILED",
        "unsupported": "UNSUPPORTED",
    }.get(state, state.upper())
    color = "#b42318" if state == "failed" else "#475467"
    heading = f"{_stage_heading(selection, registry)} {label}"
    children: list[Any] = [
        html.H2(
            heading,
            style={"color": color, "fontSize": "1rem", "margin": "0"},
        ),
        html.P(
            detail.get("error", f"Stage is {label.lower()}."),
            style={"margin": "0.4rem 0"},
        ),
    ]
    if state != "failed":
        return children
    log_value = detail.get("log")
    if not log_value:
        return children
    log_path = Path(log_value)
    children.append(
        html.Div(str(log_path), style={"color": "#667085", "fontSize": "0.78rem"})
    )
    log_text = jobrunner.read_text_tail(log_path)
    if log_text:
        children.append(html.Pre(log_text, style=_PRE_STYLE))
    return children


def _render_stage_detail(
    detail: dict[str, str],
    selection: dict[str, str],
    registry: list[dict],
) -> list[Any]:
    """Render a completed summary, stage status, or quiet pending state."""
    state = detail.get("state")
    if state == "completed":
        return _artifact_detail(detail, selection, registry)
    if state in {"blocked", "failed", "unsupported"}:
        return _status_detail(detail, selection, registry)
    return [
        html.H2(
            _stage_heading(selection, registry),
            style={"fontSize": "1rem", "margin": "0"},
        ),
        html.P("Pending — this stage is waiting to run or finish."),
    ]


def _downloadable_log(
    rows: list[dict],
    selection: dict[str, str] | None,
) -> Path | None:
    """Return a known selected failure log, if it currently exists."""
    detail = _find_stage_detail(rows, selection)
    if detail is None or detail.get("state") != "failed" or not detail.get("log"):
        return None
    path = Path(detail["log"])
    return path if path.is_file() else None


def _live_log(job_id: str | None) -> tuple[str, bool, str]:
    """Return live log text, running state, and a compact job label."""
    status = execution.inspect_corpus_job(job_id)
    if status is not None:
        if status.running:
            label = "Corpus run in progress"
        elif status.success:
            label = "Corpus run completed"
        else:
            label = f"Corpus run failed (exit {status.returncode})"
        return status.log_text or "Waiting for Snakemake output…", status.running, label

    return "No corpus run log yet.", False, "Corpus not running"


def create_app(*, settings_path: Path | None = None) -> Dash:
    """Create the corpus-wide progress dashboard."""
    registry = load_registry()
    current_settings = settings.load_settings(settings_path)
    app = Dash(__name__, title="APB Studio — Corpus Runner")
    app.layout = html.Main(
        [
            dcc.Store(id="active-job-id"),
            dcc.Store(id="selected-stage"),
            dcc.Store(id="grid-revision", data=0),
            dcc.Interval(
                id="poll-corpus",
                interval=_POLL_INTERVAL_MS,
                disabled=True,
            ),
            dcc.Download(id="log-download"),
            html.H1(
                "APB Studio — Corpus Runner",
                style={"fontSize": "1.55rem", "margin": "0 0 0.75rem"},
            ),
            html.Div(
                [
                    html.Span(
                        f"Fixtures: {current_settings.test_data_root}",
                        id="source-info",
                        style={"color": "#475467", "fontSize": "0.8rem"},
                    ),
                    dcc.Input(
                        id="output-root",
                        value=str(current_settings.output_root),
                        debounce=True,
                        placeholder="Output root",
                        style={
                            "boxSizing": "border-box",
                            "flex": "1 1 24rem",
                            "fontSize": "0.86rem",
                            "height": "2rem",
                            "padding": "0 0.55rem",
                        },
                    ),
                    html.Button("Reload", id="reload", style={"height": "2rem"}),
                    html.Button(
                        "Run corpus",
                        id="run-corpus",
                        style={"height": "2rem", "fontWeight": "600"},
                    ),
                    html.Span(
                        id="run-status",
                        style={"color": "#475467", "fontSize": "0.82rem"},
                    ),
                ],
                style={
                    "alignItems": "center",
                    "display": "flex",
                    "flexWrap": "wrap",
                    "gap": "0.45rem",
                },
            ),
            html.Div(
                id="error",
                style={
                    "color": "#b42318",
                    "fontSize": "0.84rem",
                    "marginTop": "0.5rem",
                    "whiteSpace": "pre-wrap",
                },
            ),
            dag.AgGrid(
                id="corpus-grid",
                rowData=[],
                columnDefs=_column_definitions(registry),
                defaultColDef={
                    "filter": True,
                    "resizable": True,
                    "sortable": True,
                },
                dashGridOptions={
                    "animateRows": False,
                    "headerHeight": 34,
                    "pagination": True,
                    "paginationPageSize": 25,
                    "rowHeight": 32,
                },
                getRowId="params.data._row_id",
                style={"height": "560px", "marginTop": "0.75rem"},
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.H2(
                                "Artifact summary or status",
                                style={"fontSize": "1rem", "margin": "0"},
                            ),
                            html.Button(
                                "Download log",
                                id="download-log",
                                disabled=True,
                                style={"height": "1.8rem"},
                            ),
                        ],
                        style={
                            "alignItems": "center",
                            "display": "flex",
                            "justifyContent": "space-between",
                        },
                    ),
                    html.Div(
                        "Click a completed stage or a status cell.",
                        id="stage-detail",
                        style={"marginTop": "0.5rem"},
                    ),
                ],
                id="stage-detail-panel",
                style=_PANEL_STYLE,
            ),
            html.Section(
                [
                    html.H2(
                        "Snakemake log",
                        style={"fontSize": "1rem", "margin": "0"},
                    ),
                    html.Pre(id="global-log", style=_PRE_STYLE),
                ],
                id="global-log-panel",
                style=_PANEL_STYLE,
            ),
        ],
        style={
            "color": "#101828",
            "fontFamily": "Inter, system-ui, sans-serif",
            "fontSize": "0.88rem",
            "margin": "1rem auto",
            "maxWidth": "1500px",
            "padding": "0 1rem 1rem",
        },
    )

    @app.callback(
        Output("corpus-grid", "rowData"),
        Output("error", "children"),
        Output("global-log", "children"),
        Output("run-corpus", "disabled"),
        Output("poll-corpus", "disabled"),
        Output("run-status", "children"),
        Output("active-job-id", "data"),
        Output("source-info", "children"),
        Output("grid-revision", "data"),
        Input("reload", "n_clicks"),
        Input("run-corpus", "n_clicks"),
        Input("poll-corpus", "n_intervals"),
        State("output-root", "value"),
        State("active-job-id", "data"),
        State("grid-revision", "data"),
    )
    def refresh_corpus(
        _reload_clicks: int | None,
        _run_clicks: int | None,
        _tick: int,
        output_root: str,
        job_id: str | None,
        grid_revision: int | None,
    ) -> tuple[list[dict], str, str, bool, bool, str, str | None, str, int]:
        """Launch when requested, then refresh rows and the live global log."""
        launch_error = ""
        job_id = execution.active_corpus_job_id() or job_id
        if ctx.triggered_id in {"reload", "run-corpus"}:
            try:
                settings.update_settings(
                    output_root=output_root,
                    path=settings_path,
                )
                if ctx.triggered_id == "run-corpus":
                    job_id = execution.launch_corpus(
                        cores=3,
                        settings_path=settings_path,
                    )
            except (OSError, RuntimeError, ValueError) as exc:
                action = (
                    "launch corpus"
                    if ctx.triggered_id == "run-corpus"
                    else "save settings"
                )
                launch_error = f"Could not {action}: {exc}"

        rows, snapshot, load_error = _load_dashboard_rows(
            job_id,
            settings_path=settings_path,
        )
        log_text, running, status_label = _live_log(job_id)
        active_settings = settings.load_settings(settings_path)
        fixture_count = len(snapshot.fixtures) if snapshot is not None else 0
        source_label = (
            f"Fixtures: {active_settings.test_data_root}"
            f" · {fixture_count} complete · {len(rows)} branches"
        )
        errors = "\n\n".join(error for error in (load_error, launch_error) if error)
        run_disabled = running or load_error is not None
        return (
            rows,
            errors,
            log_text,
            run_disabled,
            not running,
            status_label,
            job_id,
            source_label,
            (grid_revision or 0) + 1,
        )

    @app.callback(
        Output("stage-detail", "children"),
        Output("selected-stage", "data"),
        Output("download-log", "disabled"),
        Input("corpus-grid", "cellClicked"),
        Input("grid-revision", "data"),
        State("active-job-id", "data"),
        State("selected-stage", "data"),
        prevent_initial_call=True,
    )
    def show_stage_detail(
        cell: dict[str, Any] | None,
        _grid_revision: int,
        job_id: str | None,
        selected_stage: dict[str, str] | None,
    ) -> tuple[object, object, object]:
        """Show a clicked stage and refresh that same selection while the job runs."""
        rows, _snapshot, error = _load_dashboard_rows(
            job_id,
            settings_path=settings_path,
        )
        if error is not None:
            return error, selected_stage or no_update, True
        selection = (
            _selection_from_click(cell, registry, rows)
            if ctx.triggered_id == "corpus-grid"
            else selected_stage
        )
        if selection is None:
            return no_update, no_update, no_update
        detail = _find_stage_detail(rows, selection)
        if detail is None:
            return (
                "Click a completed stage or a status cell.",
                None,
                True,
            )
        log_path = _downloadable_log(rows, selection)
        return (
            _render_stage_detail(detail, selection, registry),
            selection,
            log_path is None,
        )

    @app.callback(
        Output("log-download", "data"),
        Input("download-log", "n_clicks"),
        State("selected-stage", "data"),
        State("active-job-id", "data"),
        prevent_initial_call=True,
    )
    def download_selected_log(
        _clicks: int,
        selection: dict[str, str] | None,
        job_id: str | None,
    ) -> object:
        """Download only a currently known Target log resolved on the server."""
        rows, _snapshot, error = _load_dashboard_rows(
            job_id,
            settings_path=settings_path,
        )
        if error is not None:
            return no_update
        log_path = _downloadable_log(rows, selection)
        if log_path is None:
            return no_update
        return dcc.send_file(str(log_path), filename=log_path.name)

    return app


app = create_app()


def main() -> None:
    """Run the corpus dashboard development server."""
    app.run(debug=True, port=int(os.environ.get("APB_STUDIO_PORT", "8051")))


if __name__ == "__main__":
    main()
