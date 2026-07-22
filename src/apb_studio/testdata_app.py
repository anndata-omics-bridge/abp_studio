"""Plotly Dash browser for cataloging and downloading ProteoBench test data."""

from pathlib import Path

import dash_ag_grid as dag
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from pydantic import ValidationError

from apb_studio import module_resources
from apb_studio import settings
from apb_studio import testdata
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
    "conversion_status",
]
TABLE_HEADERS = {
    "download_status": "Download",
    "conversion_status": "Convert",
}
TABLE_COLUMN_WIDTHS = {
    "module": 125,
    "software_name": 145,
    "software_version": 125,
    "nr_feature": 100,
    "intermediate_hash": 280,
    "download_status": 120,
    "conversion_status": 190,
    "dataset": 280,
    "n_obs": 90,
    "n_var": 90,
    "layers": 180,
    "modalities": 180,
    "mudata": 85,
    "path": 420,
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
MUDATA_COLUMNS = [
    "dataset",
    "module",
    "software_name",
    "software_version",
    "n_obs",
    "n_var",
    "modalities",
    "path",
]
LEVEL_COLUMNS = [
    "dataset",
    "module",
    "software_name",
    "software_version",
    "n_obs",
    "n_var",
    "layers",
    "mudata",
    "path",
]
CONTAINER_TABLE_IDS = {
    "mudata": "anndata-mudata-table",
    **{level: f"anndata-{level}-table" for level in testdata.LEVELS},
}
CONVERSION_TARGETS = [
    {"label": "All levels", "value": testdata.ALL_LEVELS},
    *[{"label": level.title(), "value": level} for level in testdata.LEVELS],
]
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
            }
            for name in columns
        ],
        rowData=[],
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


def _selected_container_row(
    active_tab: str,
    selections: dict[str, list[dict] | None],
    triggered_id: str | None,
) -> dict | None:
    """Return only the selected row belonging to the active container view."""
    table_id = CONTAINER_TABLE_IDS.get(active_tab)
    if triggered_id in CONTAINER_TABLE_IDS.values():
        table_id = triggered_id
    selected = selections.get(table_id or "")
    return selected[0] if selected else None


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
                        "Download annotations",
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


def conversion_controls() -> html.Div:
    """Build controls for converting the selected downloaded fixture."""
    return html.Div(
        [
            html.Span(
                "Convert selected →",
                style={"fontSize": "11px", "fontWeight": "bold"},
            ),
            dcc.Checklist(
                id="convert-level",
                options=[],
                value=[],
                inline=True,
                style={"fontSize": "11px", "whiteSpace": "nowrap"},
                labelStyle={"marginRight": "0.65rem"},
            ),
            html.Button(
                "Convert",
                id="convert-button",
                disabled=True,
                style=PRIMARY_BUTTON_STYLE,
            ),
            html.Span(id="convert-hint", style={"fontSize": "11px"}),
        ],
        style={
            "display": "flex",
            "flexWrap": "wrap",
            "gap": "0.6rem",
            "alignItems": "center",
            "padding": "0.5rem 0",
        },
    )


def workflow_controls() -> html.Div:
    """Build Download/Convert subtabs and the shared collapsible job log."""
    return html.Div(
        [
            dcc.Tabs(
                [
                    dcc.Tab(
                        download_controls(),
                        label="Download",
                        value="download",
                        style=TAB_STYLE,
                        selected_style=SELECTED_TAB_STYLE,
                    ),
                    dcc.Tab(
                        conversion_controls(),
                        label="Convert",
                        value="convert",
                        style=TAB_STYLE,
                        selected_style=SELECTED_TAB_STYLE,
                    ),
                ],
                id="data-workflow-tabs",
                value="download",
            ),
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


def anndata_panel() -> html.Div:
    """Build the converted-container cross-section and summary pane."""
    tabs = [
        dcc.Tab(
            data_table(
                CONTAINER_TABLE_IDS["mudata"],
                MUDATA_COLUMNS,
                height="30vh",
            ),
            label="MuData",
            value="mudata",
            style=TAB_STYLE,
            selected_style=SELECTED_TAB_STYLE,
        )
    ]
    tabs.extend(
        dcc.Tab(
            data_table(CONTAINER_TABLE_IDS[level], LEVEL_COLUMNS, height="30vh"),
            label=level.title(),
            value=level,
            style=TAB_STYLE,
            selected_style=SELECTED_TAB_STYLE,
        )
        for level in testdata.LEVELS
    )
    return html.Div(
        [
            dcc.Tabs(tabs, id="anndata-level-tabs", value="mudata"),
            html.H2(
                "Descriptive summary",
                style={"fontSize": "15px", "margin": "0.6rem 0 0.35rem"},
            ),
            html.Pre(
                "Select a container.",
                id="anndata-summary",
                style={
                    **PRE_STYLE,
                    "height": "34vh",
                    "border": "1px solid #cfd3dc",
                    "padding": "0.6rem",
                },
            ),
        ]
    )


def data_panel() -> html.Div:
    """Build one fixture table with download/conversion workflows and details."""
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
    """Build managed annotation status and optional FASTA overrides."""
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
                        "Annotations are downloaded from ProteoBench module_settings.toml",
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
            data_table("resource-table", RESOURCE_COLUMNS, height="55vh"),
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


def create_app(*, settings_path: Path | None = None) -> Dash:
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
            dcc.Store(id="selected-fixture"),
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
                        anndata_panel(),
                        label="AnnData",
                        value="anndata",
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

    @app.callback(
        Output("job-id", "data"),
        Input("catalog-button", "n_clicks"),
        Input("select-button", "n_clicks"),
        Input("download-button", "n_clicks"),
        Input("annotations-button", "n_clicks"),
        Input("fasta-button", "n_clicks"),
        Input("clean-button", "n_clicks"),
        Input("convert-button", "n_clicks"),
        State("strategy", "value"),
        State("module", "value"),
        State("selected-fixture", "data"),
        State("convert-level", "value"),
        State("storage-root", "data"),
        State("job-id", "data"),
        prevent_initial_call=True,
    )
    def run_action(
        _catalog: int | None,
        _select: int | None,
        _download: int | None,
        _annotations: int | None,
        _fasta: int | None,
        _clean: int | None,
        _convert: int | None,
        strategy: str,
        module: str | None,
        selected_fixture: dict | None,
        convert_levels: list[str] | None,
        data_root: str,
        active_job_id: str | None,
    ) -> str:
        active_status = testdata.job_status(active_job_id)
        if active_status is not None and active_status.running:
            raise PreventUpdate
        action = ctx.triggered_id.removesuffix("-button")
        paths = testdata.TestDataPaths(data_dir=data_root)
        try:
            if action == "convert":
                if not selected_fixture or not convert_levels:
                    raise PreventUpdate
                return testdata.launch_convert(paths, selected_fixture, convert_levels)
            return testdata.launch(action, paths, strategy=strategy, module=module)
        except testdata.JobAlreadyRunningError as error:
            raise PreventUpdate from error

    @app.callback(
        Output("job-log-details", "open"),
        Input("job-id", "data"),
        prevent_initial_call=True,
    )
    def open_log_for_new_job(job_id: str | None) -> bool:
        """Reveal command output whenever a new background job starts."""
        return bool(job_id)

    @app.callback(
        Output("storage-root", "data"),
        Output("storage-message", "children"),
        Output("storage-message", "style"),
        Input("storage-apply-button", "n_clicks"),
        State("storage-folder", "value"),
        State("job-id", "data"),
        prevent_initial_call=True,
    )
    def apply_storage_folder(
        _clicks: int,
        folder: str | None,
        job_id: str | None,
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
            paths = testdata.TestDataPaths(data_dir=folder or "")
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

    @app.callback(
        Output("storage-folder", "value"),
        Output("storage-summary", "children"),
        Input("storage-root", "data"),
    )
    def show_storage_paths(data_root: str) -> tuple[str, str]:
        """Show the active root and every path derived from it."""
        paths = testdata.TestDataPaths(data_dir=data_root)
        return str(paths.data_dir), testdata.storage_summary(paths)

    @app.callback(
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
    )
    def refresh(
        _tick: int,
        data_root: str,
        job_id: str | None,
    ) -> tuple[
        list[dict],
        list[dict],
        str,
        str,
        str,
        dict[str, str],
        list[dict],
        list[dict],
    ]:
        paths = testdata.TestDataPaths(data_dir=data_root)
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

    @app.callback(
        Output("resource-fasta", "value"),
        Input("resource-module", "value"),
        Input("storage-root", "data"),
    )
    def show_module_resource(
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

    @app.callback(
        Output("resource-message", "children"),
        Output("resource-message", "style"),
        Input("resource-save-button", "n_clicks"),
        State("resource-module", "value"),
        State("resource-fasta", "value"),
        State("storage-root", "data"),
        prevent_initial_call=True,
    )
    def save_module_resource(
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

    @app.callback(
        Output("convert-level", "options"),
        Output("convert-level", "value"),
        Output("convert-hint", "children"),
        Input("selected-fixture", "data"),
    )
    def select_conversion_targets(
        row: dict | None,
    ) -> tuple[list[dict], list[str], str]:
        """Offer only conversion targets supported by the selected fixture."""
        if not row:
            return [], [], "Select a fixture."
        targets = row.get("conversion_targets", [])
        options = [
            option for option in CONVERSION_TARGETS if option["value"] in targets
        ]
        if not options:
            return [], [], row.get("conversion_status", "Not convertible.")
        return options, [options[0]["value"]], row["conversion_status"]

    @app.callback(
        Output("convert-button", "disabled"),
        Input("selected-fixture", "data"),
        Input("convert-level", "value"),
    )
    def toggle_convert_button(row: dict | None, levels: list[str] | None) -> bool:
        """Disable conversion until a fixture and at least one level are selected."""
        return not row or not levels

    @app.callback(
        Output(CONTAINER_TABLE_IDS["mudata"], "rowData"),
        Output(CONTAINER_TABLE_IDS["ion"], "rowData"),
        Output(CONTAINER_TABLE_IDS["fragment"], "rowData"),
        Output(CONTAINER_TABLE_IDS["peptidoform"], "rowData"),
        Output(CONTAINER_TABLE_IDS["peptide"], "rowData"),
        Output(CONTAINER_TABLE_IDS["protein"], "rowData"),
        Input("poll", "n_intervals"),
        Input("storage-root", "data"),
        State("job-id", "data"),
    )
    def refresh_containers(
        _tick: int,
        data_root: str,
        job_id: str | None,
    ) -> tuple[object, object, object, object, object, object]:
        """Refresh converted rows without reading a container being written."""
        status = testdata.job_status(job_id)
        if status is not None and status.running:
            return (no_update,) * 6
        paths = testdata.TestDataPaths(data_dir=data_root)
        tables = testdata.container_rows(paths)
        return (
            tables["mudata"],
            tables["ion"],
            tables["fragment"],
            tables["peptidoform"],
            tables["peptide"],
            tables["protein"],
        )

    @app.callback(
        Output("anndata-summary", "children"),
        Input("anndata-level-tabs", "value"),
        Input(CONTAINER_TABLE_IDS["mudata"], "selectedRows"),
        Input(CONTAINER_TABLE_IDS["ion"], "selectedRows"),
        Input(CONTAINER_TABLE_IDS["fragment"], "selectedRows"),
        Input(CONTAINER_TABLE_IDS["peptidoform"], "selectedRows"),
        Input(CONTAINER_TABLE_IDS["peptide"], "selectedRows"),
        Input(CONTAINER_TABLE_IDS["protein"], "selectedRows"),
        Input("storage-root", "data"),
    )
    def show_container_summary(
        active_tab: str,
        mudata_selected: list[dict] | None,
        ion_selected: list[dict] | None,
        fragment_selected: list[dict] | None,
        peptidoform_selected: list[dict] | None,
        peptide_selected: list[dict] | None,
        protein_selected: list[dict] | None,
        _data_root: str,
    ) -> str:
        """Show the exact standalone, MuData, or MuData-modality target selected."""
        if ctx.triggered_id == "storage-root":
            return "Select a container."
        selections = {
            CONTAINER_TABLE_IDS["mudata"]: mudata_selected,
            CONTAINER_TABLE_IDS["ion"]: ion_selected,
            CONTAINER_TABLE_IDS["fragment"]: fragment_selected,
            CONTAINER_TABLE_IDS["peptidoform"]: peptidoform_selected,
            CONTAINER_TABLE_IDS["peptide"]: peptide_selected,
            CONTAINER_TABLE_IDS["protein"]: protein_selected,
        }
        row = _selected_container_row(active_tab, selections, ctx.triggered_id)
        if row is None:
            return "Select a container."
        return testdata.container_summary(row["path"], row.get("modality"))

    @app.callback(
        Output("workspace-tabs", "value"),
        Output("finished-job-id", "data"),
        Input("poll", "n_intervals"),
        State("job-id", "data"),
        State("finished-job-id", "data"),
        State("storage-root", "data"),
        prevent_initial_call=True,
    )
    def show_completed_job(
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
        destination = (
            "anndata"
            if len(status.command) > 1 and status.command[1] == "convert"
            else "data"
        )
        return destination, job_id

    @app.callback(
        Output("file-info", "children"),
        Output("submission-json", "children"),
        Output("parameters", "children"),
        Output("selected-fixture", "data"),
        Input("catalog-table", "selectedRows"),
        Input("storage-root", "data"),
    )
    def show_details(
        catalog_selected: list[dict] | None,
        data_root: str,
    ) -> tuple[str, str, str, dict | None]:
        if ctx.triggered_id == "storage-root":
            return "Select a row.", "", "", None
        row = catalog_selected[0] if catalog_selected else None
        paths = testdata.TestDataPaths(data_dir=data_root)
        return (*testdata.row_details(paths, row), row)

    register_configuration_callbacks(app)
    return app


app = create_app()


def main() -> None:
    """Run the test-data dashboard development server."""
    app.run(debug=True)


if __name__ == "__main__":
    main()
