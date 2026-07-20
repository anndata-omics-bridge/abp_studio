"""Plotly Dash browser for cataloging and downloading ProteoBench test data."""

import dash_ag_grid as dag
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update
from pydantic import ValidationError

from apb_studio import testdata

DEFAULT_PATHS = testdata.TestDataPaths()
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
TABLE_COLUMN_WIDTHS = {
    "module": 125,
    "software_name": 145,
    "software_version": 125,
    "nr_feature": 100,
    "intermediate_hash": 280,
    "download_status": 120,
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


def data_table(table_id: str) -> dag.AgGrid:
    """Create a filterable single-row-select data table."""
    return dag.AgGrid(
        id=table_id,
        columnDefs=[
            {
                "field": name,
                "filter": True,
                "headerName": name.replace("_", " ").title(),
                "width": TABLE_COLUMN_WIDTHS[name],
            }
            for name in TABLE_COLUMNS
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
            "height": "34vh",
            "minHeight": "280px",
            "fontSize": "11px",
            "--ag-font-size": "11px",
            "--ag-grid-size": "3px",
        },
    )


def action_panel() -> html.Div:
    """Build the compact command bar and live job log."""
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
                        "Clean generated data",
                        id="clean-button",
                        style=BUTTON_STYLE,
                    ),
                ],
                style={
                    "display": "flex",
                    "gap": "0.6rem",
                    "alignItems": "center",
                    "padding": "0.5rem 0",
                },
            ),
            html.Pre(
                id="job-log",
                style={
                    **PRE_STYLE,
                    "height": "34vh",
                    "minHeight": "280px",
                    "border": "1px solid #e2e2e2",
                    "padding": "0.5rem",
                },
            ),
        ]
    )


def data_panel() -> html.Div:
    """Build the catalog and download-selection tables."""
    return html.Div(
        [
            html.Section(
                [
                    html.H2(
                        "Catalog", style={"fontSize": "15px", "margin": "0.4rem 0"}
                    ),
                    data_table("catalog-table"),
                ]
            ),
            html.Section(
                [
                    html.H2(
                        "Selected for download",
                        style={"fontSize": "15px", "margin": "0.4rem 0"},
                    ),
                    data_table("selection-table"),
                ]
            ),
        ],
        style={
            "display": "grid",
            "gridTemplateColumns": "1fr 1fr",
            "gap": "0.75rem",
        },
    )


def storage_panel() -> html.Div:
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
                        value=str(DEFAULT_PATHS.data_dir),
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


def detail_tabs() -> dcc.Tabs:
    """Build the always-visible row-detail tabs."""
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


def create_app() -> Dash:
    """Create the ProteoBench test-data application."""
    app = Dash(__name__, title="APB Studio — test data")
    app.layout = html.Main(
        [
            html.Div(
                [
                    html.H1(
                        "APB Studio — ProteoBench test data",
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
                data=str(DEFAULT_PATHS.data_dir),
                storage_type="local",
            ),
            dcc.Tabs(
                [
                    dcc.Tab(
                        action_panel(),
                        id="actions-tab",
                        label="Actions",
                        value="actions",
                        style=TAB_STYLE,
                        selected_style=SELECTED_TAB_STYLE,
                    ),
                    dcc.Tab(
                        data_panel(),
                        label="Data",
                        value="data",
                        style=TAB_STYLE,
                        selected_style=SELECTED_TAB_STYLE,
                    ),
                    dcc.Tab(
                        storage_panel(),
                        label="Storage",
                        value="storage",
                        style=TAB_STYLE,
                        selected_style=SELECTED_TAB_STYLE,
                    ),
                ],
                id="workspace-tabs",
                value="data",
            ),
            detail_tabs(),
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
        Input("clean-button", "n_clicks"),
        State("strategy", "value"),
        State("module", "value"),
        State("storage-root", "data"),
        prevent_initial_call=True,
    )
    def run_action(
        _catalog: int | None,
        _select: int | None,
        _download: int | None,
        _clean: int | None,
        strategy: str,
        module: str | None,
        data_root: str,
    ) -> str:
        action = ctx.triggered_id.removesuffix("-button")
        paths = testdata.TestDataPaths(data_dir=data_root)
        return testdata.launch(action, paths, strategy=strategy, module=module)

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
        Output("selection-table", "rowData"),
        Output("module", "options"),
        Output("status", "children"),
        Output("job-log", "children"),
        Output("actions-tab", "label"),
        Output("actions-tab", "style"),
        Output("actions-tab", "selected_style"),
        Input("poll", "n_intervals"),
        Input("storage-root", "data"),
        State("job-id", "data"),
    )
    def refresh(
        _tick: int,
        data_root: str,
        job_id: str | None,
    ) -> tuple[list[dict], list[dict], list[dict], str, str, str, dict, dict]:
        paths = testdata.TestDataPaths(data_dir=data_root)
        catalog = testdata.catalog_rows(paths)
        selection = testdata.selection_rows(paths)
        modules = sorted({row["module"] for row in catalog})
        status = testdata.job_status(job_id)
        message, log_text, log_label, log_style = testdata.job_presentation(
            status,
            catalog_count=len(catalog),
            selection_count=len(selection),
        )
        options = [{"label": value, "value": value} for value in modules]
        action_label = log_label.replace("Log", "Actions", 1)
        action_style = {**TAB_STYLE, **log_style}
        selected_action_style = {**SELECTED_TAB_STYLE, **log_style}
        return (
            catalog,
            selection,
            options,
            message,
            log_text,
            action_label,
            action_style,
            selected_action_style,
        )

    @app.callback(
        Output("workspace-tabs", "value"),
        Output("finished-job-id", "data"),
        Input("poll", "n_intervals"),
        State("job-id", "data"),
        State("finished-job-id", "data"),
        prevent_initial_call=True,
    )
    def show_completed_job(
        _tick: int,
        job_id: str | None,
        finished_job_id: str | None,
    ) -> tuple[object, object]:
        """Show data after success and leave failed-job logs visible."""
        if not job_id or job_id == finished_job_id:
            return no_update, no_update
        status = testdata.job_status(job_id)
        if status is None or status.running:
            return no_update, no_update
        return ("data" if status.success else "actions"), job_id

    @app.callback(
        Output("file-info", "children"),
        Output("submission-json", "children"),
        Output("parameters", "children"),
        Input("catalog-table", "selectedRows"),
        Input("selection-table", "selectedRows"),
        Input("storage-root", "data"),
    )
    def show_details(
        catalog_selected: list[dict] | None,
        selection_selected: list[dict] | None,
        data_root: str,
    ) -> tuple[str, str, str]:
        source = ctx.triggered_id
        if source == "storage-root":
            return "Select a row.", "", ""
        selected = catalog_selected if source == "catalog-table" else selection_selected
        row = selected[0] if selected else None
        paths = testdata.TestDataPaths(data_dir=data_root)
        return testdata.row_details(paths, row)

    return app


app = create_app()


def main() -> None:
    """Run the test-data dashboard development server."""
    app.run(debug=True)


if __name__ == "__main__":
    main()
