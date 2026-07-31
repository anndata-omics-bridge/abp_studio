"""Plotly Dash browser for cataloging and downloading ProteoBench test data."""

from functools import partial
from itertools import islice
from pathlib import Path
from typing import Any

import dash_ag_grid as dag
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from pydantic import ValidationError

from apb_studio import module_resources, settings, testdata
from apb_studio.config_panel import (
    configuration_panel,
    register_configuration_callbacks,
)

DEFAULT_PATHS = testdata.TestDataPaths(
    data_dir=settings.load_settings().test_data_root,
)
STRATEGIES = [
    {
        "label": "Smallest per software/version",
        "value": "smallest-per-software-version",
    },
    {"label": "Smallest per software", "value": "smallest-per-software"},
    {"label": "Smallest per module", "value": "smallest-per-module"},
    {"label": "All", "value": "all"},
]
TABLE_COLUMNS = [
    "module",
    "software_name",
    "software_version",
    "nr_feature",
    "intermediate_hash",
    "download_status",
]
TABLE_HEADERS = {
    "download_status": "Download",
}
TABLE_COLUMN_WIDTHS = {
    "module": 125,
    "software_name": 145,
    "software_version": 125,
    "nr_feature": 100,
    "intermediate_hash": 280,
    "download_status": 120,
    "annotation_path": 420,
    "annotation_status": 105,
    "fasta_path": 420,
    "fasta_status": 105,
}
RESOURCE_COLUMNS = [
    "module",
    "annotation_status",
    "annotation_path",
    "fasta_status",
    "fasta_path",
]
_RESOURCE_PREVIEW_KIND = {
    "annotation_status": "annotation",
    "annotation_path": "annotation",
    "fasta_status": "FASTA",
    "fasta_path": "FASTA",
}
_RESOURCE_PREVIEW_PROMPT = "Click an annotation or FASTA status/path cell to preview its content."
_FASTA_PREVIEW_LINES = 40
_CLICKABLE_CELL_STYLE = {
    "color": "#175cd3",
    "cursor": "pointer",
    "textDecoration": "underline",
}
BUTTON_STYLE = {
    "fontSize": "11px",
    "padding": "0.3rem 0.55rem",
    "whiteSpace": "nowrap",
}
PRIMARY_BUTTON_STYLE = {
    **BUTTON_STYLE,
    "backgroundColor": "#6f42c1",
    "border": "0",
    "borderRadius": "3px",
    "color": "white",
    "fontWeight": "bold",
}
TAB_STYLE = {
    "fontSize": "10px",
    "height": "28px",
    "lineHeight": "18px",
    "padding": "4px",
}
SELECTED_TAB_STYLE = {
    **TAB_STYLE,
    "borderTop": "2px solid #6f42c1",
    "color": "#38206e",
}
PRE_STYLE = {
    "fontSize": "11px",
    "lineHeight": "1.25",
    "margin": "0",
    "overflow": "auto",
    "whiteSpace": "pre-wrap",
}


def data_table(
    table_id: str,
    columns: list[str] | None = None,
    *,
    height: str = "34vh",
    row_id_field: str | None = None,
) -> dag.AgGrid:
    """Create a filterable single-row-select data table."""
    columns = columns or TABLE_COLUMNS
    return dag.AgGrid(
        id=table_id,
        columnDefs=[
            {
                "field": name,
                "filter": True,
                "headerName": TABLE_HEADERS.get(name, name.replace("_", " ").title()),
                "width": TABLE_COLUMN_WIDTHS.get(name, 130),
                **({"cellStyle": _CLICKABLE_CELL_STYLE} if name in _RESOURCE_PREVIEW_KIND else {}),
            }
            for name in columns
        ],
        rowData=[],
        getRowId=f"params.data.{row_id_field}" if row_id_field is not None else None,
        dashGridOptions={
            "pagination": False,
            "alwaysShowVerticalScroll": True,
            "rowHeight": 27,
            "headerHeight": 30,
            "rowSelection": {
                "mode": "singleRow",
                "checkboxes": False,
                "enableClickSelection": True,
            },
        },
        defaultColDef={"sortable": True, "resizable": True},
        style={
            "height": height,
            "minHeight": "280px",
            "fontSize": "11px",
            "--ag-font-size": "11px",
            "--ag-grid-size": "3px",
        },
    )


def download_controls() -> html.Div:
    """Build catalog, selection, and download controls."""
    return html.Div(
        [
            html.Div(
                [
                    html.Button("Catalog", id="catalog-button", style=BUTTON_STYLE),
                    dcc.RadioItems(
                        id="strategy",
                        options=STRATEGIES,
                        value="smallest-per-software-version",
                        inline=True,
                        style={"fontSize": "11px", "whiteSpace": "nowrap"},
                        labelStyle={"marginRight": "0.65rem"},
                    ),
                    dcc.Dropdown(
                        id="module",
                        placeholder="All modules",
                        clearable=True,
                        style={"fontSize": "11px", "minWidth": "220px"},
                    ),
                    html.Button(
                        "Create selection",
                        id="select-button",
                        style=PRIMARY_BUTTON_STYLE,
                    ),
                    html.Button(
                        "Download selected",
                        id="download-button",
                        style=BUTTON_STYLE,
                    ),
                    html.Button(
                        "Download module + scoring settings",
                        id="annotations-button",
                        style=BUTTON_STYLE,
                    ),
                    html.Button(
                        "Download FASTAs",
                        id="fasta-button",
                        style=BUTTON_STYLE,
                    ),
                    html.Button(
                        "Clean generated data",
                        id="clean-button",
                        style=BUTTON_STYLE,
                    ),
                ],
                style={
                    "display": "flex",
                    "flexWrap": "wrap",
                    "gap": "0.6rem",
                    "alignItems": "center",
                    "padding": "0.5rem 0",
                },
            ),
        ]
    )


def workflow_controls() -> html.Div:
    """Build download controls and the shared collapsible job log."""
    return html.Div(
        [
            download_controls(),
            html.Details(
                [
                    html.Summary(
                        "Log",
                        id="job-log-summary",
                        style={"cursor": "pointer", "fontSize": "11px"},
                    ),
                    html.Pre(
                        id="job-log",
                        style={
                            **PRE_STYLE,
                            "border": "1px solid #e2e2e2",
                            "maxHeight": "22vh",
                            "padding": "0.5rem",
                        },
                    ),
                ],
                id="job-log-details",
                style={"margin": "0.25rem 0"},
            ),
        ]
    )


def _resource_selection(cell: dict[str, Any] | None) -> tuple[str, str] | None:
    """Resolve a resource-grid event to a module and preview kind."""
    if not cell or cell.get("colId") not in _RESOURCE_PREVIEW_KIND:
        return None
    module = cell.get("rowId")
    if not isinstance(module, str) or not module:
        return None
    return module, _RESOURCE_PREVIEW_KIND[str(cell["colId"])]


def _resource_preview(cell: dict[str, Any] | None, data_root: str) -> str:
    """Read one server-resolved annotation or bounded FASTA preview."""
    selection = _resource_selection(cell)
    if selection is None:
        return _RESOURCE_PREVIEW_PROMPT
    module, kind = selection
    resource = module_resources.load_module_resources(data_root).for_module(module)
    if resource is None:
        return f"No resource assignment found for module {module}."

    path = resource.annotation_path if kind == "annotation" else resource.fasta_path
    error = resource.annotation_error if kind == "annotation" else resource.fasta_error
    if path is None:
        return f"No {kind} resource is assigned for module {module}."
    if error is not None:
        return f"{kind} · {path}\n\n{error}"
    try:
        if kind == "annotation":
            content = path.read_text(encoding="utf-8", errors="replace")
            content = content or "(empty file)"
        else:
            with path.open(encoding="utf-8", errors="replace") as stream:
                lines = list(islice(stream, _FASTA_PREVIEW_LINES + 1))
            truncated = len(lines) > _FASTA_PREVIEW_LINES
            content = "".join(lines[:_FASTA_PREVIEW_LINES]).rstrip()
            content = content or "(empty file)"
            if truncated:
                content = f"{content}\n… preview truncated after {_FASTA_PREVIEW_LINES} lines"
    except OSError as exc:
        return f"Could not read {kind} resource {path}: {exc}"
    return f"{kind} · {path}\n\n{content}"


def data_panel() -> html.Div:
    """Build one fixture table with download workflows and source details."""
    return html.Div(
        [
            workflow_controls(),
            html.H2(
                "Available fixtures",
                style={"fontSize": "15px", "margin": "0.4rem 0"},
            ),
            data_table("catalog-table", height="40vh"),
            detail_tabs(),
        ],
    )


def storage_panel(paths: testdata.TestDataPaths = DEFAULT_PATHS) -> html.Div:
    """Build the test-data root editor and derived-path display."""
    return html.Div(
        [
            html.Div(
                [
                    html.Label(
                        "Test-data root folder",
                        htmlFor="storage-folder",
                        style={"fontWeight": "bold", "whiteSpace": "nowrap"},
                    ),
                    dcc.Input(
                        id="storage-folder",
                        type="text",
                        value=str(paths.data_dir),
                        style={
                            "flex": "1",
                            "fontFamily": "monospace",
                            "fontSize": "11px",
                            "minWidth": "500px",
                            "padding": "0.35rem",
                        },
                    ),
                    html.Button(
                        "Apply folder",
                        id="storage-apply-button",
                        style=PRIMARY_BUTTON_STYLE,
                    ),
                    html.Span(id="storage-message", style={"fontSize": "11px"}),
                ],
                style={
                    "display": "flex",
                    "gap": "0.65rem",
                    "alignItems": "center",
                    "padding": "0.65rem 0",
                },
            ),
            html.P(
                "Catalogs, downloaded metadata and raw files, and manifests are kept "
                "below this folder. Studio logs use the operating-system cache.",
                style={"fontSize": "11px", "margin": "0 0 0.5rem"},
            ),
            html.Pre(
                id="storage-summary",
                style={
                    **PRE_STYLE,
                    "border": "1px solid #cfd3dc",
                    "padding": "0.6rem",
                },
            ),
        ],
        style={"minHeight": "34vh"},
    )


def resources_panel() -> html.Div:
    """Build managed module-settings status and optional FASTA overrides."""
    return html.Div(
        [
            html.Div(
                [
                    dcc.Dropdown(
                        id="resource-module",
                        placeholder="Module",
                        clearable=False,
                        style={"fontSize": "11px", "minWidth": "220px"},
                    ),
                    html.Span(
                        "Module settings come from ProteoBench",
                        style={"fontSize": "11px", "color": "#555"},
                    ),
                    dcc.Input(
                        id="resource-fasta",
                        type="text",
                        placeholder="/absolute/path/to/reference.fasta",
                        style={
                            "flex": "1",
                            "fontFamily": "monospace",
                            "fontSize": "11px",
                            "padding": "0.35rem",
                        },
                    ),
                    html.Button(
                        "Save FASTA override",
                        id="resource-save-button",
                        style=PRIMARY_BUTTON_STYLE,
                    ),
                ],
                style={
                    "display": "flex",
                    "gap": "0.6rem",
                    "alignItems": "center",
                    "padding": "0.65rem 0",
                },
            ),
            html.Div(id="resource-message", style={"fontSize": "11px"}),
            data_table(
                "resource-table",
                RESOURCE_COLUMNS,
                height="36vh",
                row_id_field="module",
            ),
            html.H2(
                "Resource preview",
                style={"fontSize": "15px", "margin": "0.6rem 0 0.35rem"},
            ),
            html.Pre(
                _RESOURCE_PREVIEW_PROMPT,
                id="resource-preview",
                style={
                    **PRE_STYLE,
                    "border": "1px solid #cfd3dc",
                    "height": "28vh",
                    "padding": "0.6rem",
                },
            ),
        ]
    )


def detail_tabs() -> dcc.Tabs:
    """Build row-detail tabs shown only inside the Data workspace."""
    details_style = {
        **PRE_STYLE,
        "height": "38vh",
        "border": "1px solid #cfd3dc",
        "borderTop": "0",
        "boxSizing": "border-box",
        "padding": "0.6rem",
    }
    return dcc.Tabs(
        [
            dcc.Tab(
                html.Pre(id="file-info", style=details_style),
                label="File",
                style=TAB_STYLE,
                selected_style=SELECTED_TAB_STYLE,
            ),
            dcc.Tab(
                html.Pre(id="submission-json", style=details_style),
                label="Submission JSON",
                style=TAB_STYLE,
                selected_style=SELECTED_TAB_STYLE,
            ),
            dcc.Tab(
                html.Pre(id="parameters", style=details_style),
                label="Parameters",
                style=TAB_STYLE,
                selected_style=SELECTED_TAB_STYLE,
            ),
        ]
    )


def _run_action(
    _catalog: int | None,
    _select: int | None,
    _download: int | None,
    _annotations: int | None,
    _fasta: int | None,
    _clean: int | None,
    strategy: str,
    module: str | None,
    data_root: str,
    active_job_id: str | None,
) -> str:
    """Launch the requested fixture-management action."""
    active_status = testdata.job_status(active_job_id)
    if active_status is not None and active_status.running:
        raise PreventUpdate
    triggered_id = ctx.triggered_id
    if not isinstance(triggered_id, str):
        raise PreventUpdate
    action = triggered_id.removesuffix("-button")
    paths = testdata.TestDataPaths(data_dir=Path(data_root))
    try:
        return testdata.launch(action, paths, strategy=strategy, module=module)
    except testdata.JobAlreadyRunningError as error:
        raise PreventUpdate from error


def _open_log_for_new_job(job_id: str | None) -> bool:
    """Reveal command output whenever a new background job starts."""
    return bool(job_id)


def _apply_storage_folder(
    _clicks: int,
    folder: str | None,
    job_id: str | None,
    *,
    settings_path: Path | None,
) -> tuple[object, str, dict[str, str]]:
    """Validate, create, and activate a test-data root folder."""
    status = testdata.job_status(job_id)
    if status is not None and status.running:
        return (
            no_update,
            "Wait for the current job to finish.",
            {"color": "#b00020", "fontSize": "11px"},
        )
    try:
        paths = testdata.TestDataPaths(data_dir=Path(folder or ""))
        paths.create()
        settings.update_settings(
            test_data_root=paths.data_dir,
            path=settings_path,
        )
    except ValidationError as error:
        message = str(error.errors()[0]["msg"]).removeprefix("Value error, ")
        return (
            no_update,
            message,
            {"color": "#b00020", "fontSize": "11px"},
        )
    except OSError as error:
        return (
            no_update,
            str(error),
            {"color": "#b00020", "fontSize": "11px"},
        )
    return (
        str(paths.data_dir),
        "Folder applied.",
        {"color": "#16733c", "fontSize": "11px"},
    )


def _show_storage_paths(data_root: str) -> tuple[str, str]:
    """Show the active root and every path derived from it."""
    paths = testdata.TestDataPaths(data_dir=Path(data_root))
    return str(paths.data_dir), testdata.storage_summary(paths)


def _refresh(
    _tick: int,
    data_root: str,
    job_id: str | None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    str,
    str,
    str,
    dict[str, str],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Refresh the fixture catalog, job state, and resource inventory."""
    paths = testdata.TestDataPaths(data_dir=Path(data_root))
    catalog = testdata.catalog_rows(paths)
    modules = sorted({row["module"] for row in catalog})
    selection_count = len(testdata.read_rows(paths.selection_csv))
    status = testdata.job_status(job_id)
    message, log_text, log_label, log_style = testdata.job_presentation(
        status,
        catalog_count=len(catalog),
        selection_count=selection_count,
    )
    options = [{"label": value, "value": value} for value in modules]
    resources = module_resources.load_module_resources(paths)
    return (
        catalog,
        options,
        message,
        log_text,
        log_label,
        {"cursor": "pointer", "fontSize": "11px", **log_style},
        module_resources.resource_rows(resources, modules),
        options,
    )


def _show_module_resource(
    module: str | None,
    data_root: str,
) -> str:
    """Populate the editor with the selected module's assignments."""
    if not module:
        return ""
    resource = module_resources.load_module_resources(data_root).for_module(module)
    if resource is None:
        return ""
    return str(resource.fasta_path) if resource.fasta_path else ""


def _save_module_resource(
    _clicks: int,
    module: str | None,
    fasta_path: str | None,
    data_root: str,
) -> tuple[str, dict[str, str]]:
    """Validate and atomically save one resource assignment."""
    if not module:
        return "Choose a module.", {"color": "#b00020", "fontSize": "11px"}
    try:
        module_resources.set_module_resource(
            data_root,
            module,
            annotation_path=None,
            fasta_path=fasta_path,
        )
    except (OSError, ValueError, ValidationError) as error:
        return str(error), {"color": "#b00020", "fontSize": "11px"}
    return "Assignment saved.", {"color": "#16733c", "fontSize": "11px"}


def _show_resource_preview(
    cell: dict[str, Any] | None,
    data_root: str,
) -> str:
    """Show the clicked server-side resource, resetting when storage changes."""
    selected_cell = cell if ctx.triggered_id == "resource-table" else None
    return _resource_preview(selected_cell, data_root)


def _show_completed_job(
    _tick: int,
    job_id: str | None,
    finished_job_id: str | None,
    data_root: str,
) -> tuple[object, object]:
    """Show data after success and leave failed-job logs visible."""
    if not job_id or job_id == finished_job_id:
        return no_update, no_update
    status = testdata.job_status(job_id)
    if status is None or status.running:
        return no_update, no_update
    if not status.success:
        return "data", job_id
    action = status.command[1] if len(status.command) > 1 else ""
    if action in {"annotations", "fasta"}:
        if action == "fasta":
            inventory = testdata.fixture_inventory.load_fixture_inventory(data_root)
            module_resources.sync_fasta_resources(
                data_root,
                (fixture.module for fixture in inventory.fixtures),
            )
        return "resources", job_id
    return "data", job_id


def _show_details(
    catalog_selected: list[dict[str, Any]] | None,
    data_root: str,
) -> tuple[str, str, str]:
    """Show source details for the selected fixture row."""
    if ctx.triggered_id == "storage-root":
        return "Select a row.", "", ""
    row = catalog_selected[0] if catalog_selected else None
    paths = testdata.TestDataPaths(data_dir=Path(data_root))
    return testdata.row_details(paths, row)


def _register_testdata_callbacks(
    app: Dash,
    settings_path: Path | None,
) -> None:
    """Register Fixture Manager callbacks."""
    app.callback(
        Output("job-id", "data"),
        Input("catalog-button", "n_clicks"),
        Input("select-button", "n_clicks"),
        Input("download-button", "n_clicks"),
        Input("annotations-button", "n_clicks"),
        Input("fasta-button", "n_clicks"),
        Input("clean-button", "n_clicks"),
        State("strategy", "value"),
        State("module", "value"),
        State("storage-root", "data"),
        State("job-id", "data"),
        prevent_initial_call=True,
    )(_run_action)
    app.callback(
        Output("job-log-details", "open"),
        Input("job-id", "data"),
        prevent_initial_call=True,
    )(_open_log_for_new_job)
    app.callback(
        Output("storage-root", "data"),
        Output("storage-message", "children"),
        Output("storage-message", "style"),
        Input("storage-apply-button", "n_clicks"),
        State("storage-folder", "value"),
        State("job-id", "data"),
        prevent_initial_call=True,
    )(partial(_apply_storage_folder, settings_path=settings_path))
    app.callback(
        Output("storage-folder", "value"),
        Output("storage-summary", "children"),
        Input("storage-root", "data"),
    )(_show_storage_paths)
    app.callback(
        Output("catalog-table", "rowData"),
        Output("module", "options"),
        Output("status", "children"),
        Output("job-log", "children"),
        Output("job-log-summary", "children"),
        Output("job-log-summary", "style"),
        Output("resource-table", "rowData"),
        Output("resource-module", "options"),
        Input("poll", "n_intervals"),
        Input("storage-root", "data"),
        State("job-id", "data"),
    )(_refresh)
    app.callback(
        Output("resource-fasta", "value"),
        Input("resource-module", "value"),
        Input("storage-root", "data"),
    )(_show_module_resource)
    app.callback(
        Output("resource-message", "children"),
        Output("resource-message", "style"),
        Input("resource-save-button", "n_clicks"),
        State("resource-module", "value"),
        State("resource-fasta", "value"),
        State("storage-root", "data"),
        prevent_initial_call=True,
    )(_save_module_resource)
    app.callback(
        Output("resource-preview", "children"),
        Input("resource-table", "cellClicked"),
        Input("storage-root", "data"),
    )(_show_resource_preview)
    app.callback(
        Output("workspace-tabs", "value"),
        Output("finished-job-id", "data"),
        Input("poll", "n_intervals"),
        State("job-id", "data"),
        State("finished-job-id", "data"),
        State("storage-root", "data"),
        prevent_initial_call=True,
    )(_show_completed_job)
    app.callback(
        Output("file-info", "children"),
        Output("submission-json", "children"),
        Output("parameters", "children"),
        Input("catalog-table", "selectedRows"),
        Input("storage-root", "data"),
    )(_show_details)


def create_app(
    *,
    settings_path: Path | None = None,
) -> Dash:
    """Create the ProteoBench test-data application."""
    active_settings = settings.load_settings(settings_path)
    active_paths = testdata.TestDataPaths(data_dir=active_settings.test_data_root)
    app = Dash(__name__, title="APB Studio — Fixture Manager")
    app.layout = html.Main(
        [
            html.Div(
                [
                    html.H1(
                        "APB Studio — Fixture Manager",
                        style={"fontSize": "20px", "margin": "0"},
                    ),
                    html.Div(id="status", style={"fontSize": "11px"}),
                ],
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "baseline",
                    "marginBottom": "0.35rem",
                },
            ),
            dcc.Interval(id="poll", interval=1000, n_intervals=0),
            dcc.Store(id="job-id"),
            dcc.Store(id="finished-job-id"),
            dcc.Store(
                id="storage-root",
                data=str(active_paths.data_dir),
            ),
            dcc.Tabs(
                [
                    dcc.Tab(
                        data_panel(),
                        label="Data",
                        value="data",
                        style=TAB_STYLE,
                        selected_style=SELECTED_TAB_STYLE,
                    ),
                    dcc.Tab(
                        configuration_panel(),
                        label="Configuration",
                        value="configuration",
                        style=TAB_STYLE,
                        selected_style=SELECTED_TAB_STYLE,
                    ),
                    dcc.Tab(
                        resources_panel(),
                        label="Resources",
                        value="resources",
                        style=TAB_STYLE,
                        selected_style=SELECTED_TAB_STYLE,
                    ),
                    dcc.Tab(
                        storage_panel(active_paths),
                        label="Storage",
                        value="storage",
                        style=TAB_STYLE,
                        selected_style=SELECTED_TAB_STYLE,
                    ),
                ],
                id="workspace-tabs",
                value="data",
            ),
        ],
        style={
            "maxWidth": "1900px",
            "margin": "0.4rem auto",
            "padding": "0 0.5rem",
            "fontFamily": "sans-serif",
            "fontSize": "12px",
        },
    )

    _register_testdata_callbacks(app, settings_path)
    register_configuration_callbacks(app)
    return app


app = create_app()


def main() -> None:
    """Run the test-data dashboard development server."""
    app.run(debug=True)


if __name__ == "__main__":
    main()
