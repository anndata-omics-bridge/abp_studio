"""Dash layout and callbacks for APB's JSON configuration viewer/editor."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from dash import ALL, Dash, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from monaco_dash_editor import MonacoDashEditor

from apb_studio import config_editor

_BUTTON_STYLE = {
    "fontSize": "11px",
    "padding": "0.35rem 0.65rem",
    "cursor": "pointer",
}
_PRIMARY_BUTTON_STYLE = {
    **_BUTTON_STYLE,
    "background": "#7541c8",
    "border": "1px solid #7541c8",
    "borderRadius": "3px",
    "color": "white",
}
_EDITOR_OPTIONS = {
    "automaticLayout": True,
    "fontSize": 12,
    "formatOnType": True,
    "minimap": {"enabled": False},
    "scrollBeyondLastLine": False,
    "tabSize": 2,
    "wordWrap": "off",
}
_TAB_STYLE = {
    "fontSize": "11px",
    "height": "30px",
    "lineHeight": "20px",
    "padding": "4px 12px",
}
_SELECTED_TAB_STYLE = {
    **_TAB_STYLE,
    "borderTop": "2px solid #7541c8",
    "color": "#4f2683",
}
_CATALOG_BUTTON_STYLE = {
    "background": "transparent",
    "border": "0",
    "borderRadius": "3px",
    "cursor": "pointer",
    "display": "block",
    "fontFamily": "monospace",
    "fontSize": "10px",
    "overflow": "hidden",
    "padding": "0.28rem 0.35rem",
    "textAlign": "left",
    "textOverflow": "ellipsis",
    "whiteSpace": "nowrap",
    "width": "100%",
}


def configuration_panel() -> html.Div:
    """Build the compact document catalog and Base/level JSON tabs."""
    return html.Div(
        [
            dcc.Store(id="config-state"),
            html.Div(
                [
                    dcc.Input(
                        id="config-path",
                        placeholder="/path/to/config.json",
                        style={"flex": "1", "fontSize": "11px", "padding": "0.4rem"},
                    ),
                    dcc.Dropdown(
                        id="config-kind",
                        options=[{"label": "Parsing rule", "value": "rule"}],
                        value="rule",
                        clearable=False,
                        style={"width": "145px", "fontSize": "11px"},
                    ),
                    html.Button("Load", id="config-load", style=_BUTTON_STYLE),
                ],
                style={"display": "flex", "gap": "0.5rem", "marginBottom": "0.5rem"},
            ),
            html.Div(
                [
                    html.Section(
                        [
                            html.H2(
                                "Configuration catalog",
                                style={"fontSize": "13px", "margin": "0 0 0.4rem"},
                            ),
                            _catalog(),
                        ],
                        style={"minWidth": 0},
                    ),
                    html.Section(
                        [
                            dcc.Tabs(id="config-section-tabs", value=None),
                            MonacoDashEditor(
                                id="config-section-editor",
                                language="json",
                                value="",
                                height="64vh",
                                options=_EDITOR_OPTIONS,
                                readOnly=True,
                                theme="vs",
                            ),
                            html.Div(
                                [
                                    html.Button(
                                        "Edit",
                                        id="config-edit",
                                        disabled=True,
                                        style=_BUTTON_STYLE,
                                    ),
                                    html.Button(
                                        "Cancel",
                                        id="config-cancel",
                                        disabled=True,
                                        style=_BUTTON_STYLE,
                                    ),
                                    html.Button(
                                        "Format",
                                        id="config-format",
                                        disabled=True,
                                        style=_BUTTON_STYLE,
                                    ),
                                    html.Button(
                                        "Save",
                                        id="config-save",
                                        disabled=True,
                                        style=_PRIMARY_BUTTON_STYLE,
                                    ),
                                    html.Span(id="config-status", style={"fontSize": "11px"}),
                                    html.Span(
                                        id="config-operation",
                                        style={"fontSize": "10px"},
                                    ),
                                ],
                                style={
                                    "display": "flex",
                                    "gap": "0.5rem",
                                    "alignItems": "center",
                                    "marginTop": "0.5rem",
                                },
                            ),
                            html.Pre(
                                "",
                                id="config-issues",
                                style={
                                    "color": "#b42318",
                                    "fontSize": "10px",
                                    "margin": "0.3rem 0 0",
                                    "maxHeight": "10vh",
                                    "overflow": "auto",
                                    "whiteSpace": "pre-wrap",
                                },
                            ),
                        ],
                        style={"minWidth": 0},
                    ),
                ],
                style={
                    "display": "grid",
                    "gridTemplateColumns": "225px minmax(0, 1fr)",
                    "gap": "0.75rem",
                },
            ),
        ],
        style={"padding": "0.5rem"},
    )


def _catalog() -> html.Div:
    """Create a compact software → version-document catalog."""
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in config_editor.catalog_rows():
        grouped[row["vendor"]].append(row)
    return html.Div(
        [_software_group(vendor, grouped[vendor]) for vendor in sorted(grouped)],
        id="config-catalog",
        style={
            "border": "1px solid #d8dbe2",
            "borderRadius": "4px",
            "fontSize": "10px",
            "height": "64vh",
            "overflow": "auto",
            "padding": "0.2rem",
        },
    )


def _software_group(vendor: str, rows: list[dict[str, Any]]) -> html.Details:
    """Render all version documents for one software package."""
    return html.Details(
        [
            html.Summary(
                rows[0]["software_name"],
                style={
                    "cursor": "pointer",
                    "fontSize": "11px",
                    "fontWeight": "bold",
                    "padding": "0.35rem 0.25rem",
                },
            ),
            html.Div(
                [_document_button(row) for row in rows],
                style={"paddingLeft": "0.45rem"},
            ),
        ],
        open=True,
    )


def _document_button(row: dict[str, Any]) -> html.Button:
    """Create one selectable software-version document entry."""
    color = "#18794e" if row["valid"] else "#b42318"
    levels = ", ".join(row["levels"])
    label = f"{row['software_version']} · {levels}"
    return html.Button(
        [html.Span("● ", style={"color": color}), label],
        id={"type": "config-document", "path": row["path"]},
        n_clicks=0,
        style=_CATALOG_BUTTON_STYLE,
        title=row["path"],
    )


def _section_tabs(
    state: dict[str, Any],
    active: str,
    *,
    editing: bool,
) -> list[dcc.Tab]:
    """Build section tabs, locking navigation while a section is edited."""
    return [
        dcc.Tab(
            label=state["section_labels"][section],
            value=section,
            disabled=editing and section != active,
            style=_TAB_STYLE,
            selected_style=_SELECTED_TAB_STYLE,
        )
        for section in state["section_order"]
    ]


def register_configuration_callbacks(
    app: Dash,
) -> None:
    """Register load, section-navigation, edit, validation, and save callbacks."""
    app.callback(
        Output("config-section-editor", "value"),
        Output("config-section-editor", "readOnly"),
        Output("config-state", "data"),
        Output("config-operation", "children"),
        Output("config-path", "value"),
        Output("config-kind", "value"),
        Output("config-section-tabs", "children"),
        Output("config-section-tabs", "value"),
        Output("config-edit", "disabled"),
        Output("config-cancel", "disabled"),
        Output("config-format", "disabled"),
        Input({"type": "config-document", "path": ALL}, "n_clicks"),
        Input("config-load", "n_clicks"),
        Input("config-edit", "n_clicks"),
        Input("config-cancel", "n_clicks"),
        Input("config-format", "n_clicks"),
        Input("config-save", "n_clicks"),
        Input("config-section-tabs", "value"),
        State("config-section-editor", "value"),
        State("config-state", "data"),
        State("config-path", "value"),
        State("config-kind", "value"),
        prevent_initial_call=True,
    )(_operate_document)
    app.callback(
        Output("config-status", "children"),
        Output("config-status", "style"),
        Output("config-issues", "children"),
        Output("config-save", "disabled"),
        Input("config-section-editor", "value"),
        Input("config-state", "data"),
        Input("config-section-tabs", "value"),
    )(_validate_editor)


@dataclass(frozen=True, slots=True)
class _EditorRequest:
    document_clicks: list[int]
    active: str | None
    editor_source: str
    state: dict[str, Any] | None
    path: str | None
    kind: config_editor.ConfigKind


type _EditorResult = tuple[object, ...]
type _EditorOperation = Callable[[_EditorRequest], _EditorResult]


def _operate_document(
    document_clicks: list[int],
    _load: int | None,
    _edit: int | None,
    _cancel: int | None,
    _format: int | None,
    _save: int | None,
    active: str | None,
    editor_source: str,
    state: dict[str, Any] | None,
    path: str | None,
    kind: config_editor.ConfigKind,
) -> _EditorResult:
    """Handle document loading and the explicit per-section edit lifecycle."""
    request = _EditorRequest(
        document_clicks=document_clicks,
        active=active,
        editor_source=editor_source,
        state=state,
        path=path,
        kind=kind,
    )
    try:
        return _dispatch_editor_operation(ctx.triggered_id, request)
    except PreventUpdate:
        raise
    except (KeyError, OSError, UnicodeDecodeError, ValueError) as error:
        return _editor_error_result(error)


def _dispatch_editor_operation(trigger: object, request: _EditorRequest) -> _EditorResult:
    if isinstance(trigger, dict) and trigger.get("type") == "config-document":
        if not any(request.document_clicks):
            raise PreventUpdate
        return _loaded_result(
            config_editor.load_document(trigger["path"]),
            operation="Loaded packaged rule document.",
        )
    operation = _EDITOR_OPERATIONS.get(trigger) if isinstance(trigger, str) else None
    if operation is None:
        raise PreventUpdate
    return operation(request)


def _load_editor_path(request: _EditorRequest) -> _EditorResult:
    if not request.path:
        raise ValueError("Enter a JSON configuration path.")
    return _loaded_result(
        config_editor.load_document(request.path, kind=request.kind),
        operation="Loaded configuration.",
    )


def _active_editor(request: _EditorRequest) -> tuple[dict[str, Any], str]:
    if not request.state or not request.active:
        raise PreventUpdate
    return request.state, request.active


def _view_editor_section(request: _EditorRequest) -> _EditorResult:
    state, active = _active_editor(request)
    if state.get("editing"):
        raise PreventUpdate
    return (
        state["sections"][active],
        True,
        state,
        "Viewing raw section.",
        no_update,
        no_update,
        no_update,
        no_update,
        False,
        True,
        True,
    )


def _edit_editor_section(request: _EditorRequest) -> _EditorResult:
    state, active = _active_editor(request)
    edited = {**state, "editing": True, "active": active}
    return (
        request.editor_source,
        False,
        edited,
        f"Editing {state['section_labels'][active]}.",
        no_update,
        no_update,
        _section_tabs(edited, active, editing=True),
        no_update,
        True,
        False,
        False,
    )


def _cancel_editor_section(request: _EditorRequest) -> _EditorResult:
    state, active = _active_editor(request)
    viewed = {**state, "editing": False, "active": active}
    return (
        state["sections"][active],
        True,
        viewed,
        "Discarded in-memory changes.",
        no_update,
        no_update,
        _section_tabs(viewed, active, editing=False),
        no_update,
        False,
        True,
        True,
    )


def _format_editor_section(request: _EditorRequest) -> _EditorResult:
    state, _active = _active_editor(request)
    return (
        config_editor.format_section_source(request.editor_source),
        False,
        state,
        "Formatted in memory.",
        no_update,
        no_update,
        no_update,
        no_update,
        True,
        False,
        False,
    )


def _save_editor_section(request: _EditorRequest) -> _EditorResult:
    state, active = _active_editor(request)
    loaded = config_editor.save_section(
        state["path"],
        active,
        request.editor_source,
        document_source=state["source"],
        expected_hash=state["content_hash"],
        kind=state["kind"],
    )
    return _loaded_result(
        loaded,
        operation="Saved complete document atomically.",
        active=active,
    )


_EDITOR_OPERATIONS: dict[str, _EditorOperation] = {
    "config-load": _load_editor_path,
    "config-section-tabs": _view_editor_section,
    "config-edit": _edit_editor_section,
    "config-cancel": _cancel_editor_section,
    "config-format": _format_editor_section,
    "config-save": _save_editor_section,
}


def _editor_error_result(error: Exception) -> _EditorResult:
    return (
        no_update,
        no_update,
        no_update,
        f"Error: {error}",
        no_update,
        no_update,
        no_update,
        no_update,
        no_update,
        no_update,
        no_update,
    )


def _validate_editor(
    editor_source: str,
    state: dict[str, Any] | None,
    active: str | None,
) -> tuple[str, dict[str, str], str, bool]:
    """Continuously validate the selected raw section in document context."""
    if not state or not active:
        return "No document loaded", {"fontSize": "11px"}, "", True
    if not state.get("editing"):
        valid = state["valid"]
        issues = _format_issues(state["issues"])
        return (
            f"{'valid' if valid else 'invalid'} · read-only",
            {
                "fontSize": "11px",
                "color": "#18794e" if valid else "#b42318",
            },
            issues,
            True,
        )
    report = config_editor.validate_section(
        state["path"],
        active,
        editor_source,
        document_source=state["source"],
        kind=state["kind"],
    )
    dirty = editor_source != state["sections"][active]
    valid = report["valid"]
    label = f"{'valid' if valid else 'invalid'} · {'dirty' if dirty else 'saved'}"
    if valid:
        label += f" · checks {', '.join(report['affected'])}"
    return (
        label,
        {"fontSize": "11px", "color": "#18794e" if valid else "#b42318"},
        _format_issues(report["issues"]),
        not (valid and dirty),
    )


def _format_issues(issues: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"{issue['document'] + ': ' if issue['document'] else ''}"
        f"{issue['path']}: {issue['message']} ({issue['type']})"
        for issue in issues
    )


def _loaded_result(
    loaded: dict[str, Any],
    *,
    operation: str,
    active: str | None = None,
) -> tuple[Any, ...]:
    """Return the callback outputs for a freshly loaded document."""
    selected = str(active if active in loaded["sections"] else loaded["section_order"][0])
    state = {**loaded, "editing": False, "active": selected}
    return (
        loaded["sections"][selected],
        True,
        state,
        operation,
        loaded["path"],
        loaded["kind"],
        _section_tabs(state, selected, editing=False),
        selected,
        False,
        True,
        True,
    )
