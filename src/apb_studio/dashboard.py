"""Plotly Dash corpus overview for APB Studio."""

import dash_ag_grid as dag
from dash import Dash, Input, Output, State, dcc, html

from apb_studio import execution, pipeline
from apb_studio.registry import load_registry


def create_app() -> Dash:
    """Create the corpus dashboard."""
    app = Dash(__name__, title="APB Studio — corpus")
    app.layout = html.Main(
        [
            html.H1("APB Studio — corpus"),
            dcc.Input(id="config", value="config/corpus.yaml", style={"width": "70%"}),
            html.Button("Reload", id="reload"),
            html.Div(id="error", style={"color": "#b00020"}),
            html.Div(id="baskets"),
        ],
        style={"maxWidth": "1500px", "margin": "2rem auto", "fontFamily": "sans-serif"},
    )

    @app.callback(
        Output("baskets", "children"),
        Output("error", "children"),
        Input("reload", "n_clicks"),
        State("config", "value"),
    )
    def reload_overview(_clicks: int | None, config: str) -> tuple[list, str]:
        targets, _rows, corpus, error = execution.load_overview(config)
        if error:
            return [], error
        registry = load_registry()
        problems = pipeline.problems(corpus, targets)
        baskets = pipeline.baskets(targets, registry, problems=problems)
        blocks = []
        for name in pipeline.basket_names(registry):
            rows = baskets[name]
            blocks.extend(
                [
                    html.H2(f"{name} — {len(rows)}"),
                    dag.AgGrid(
                        rowData=rows,
                        columnDefs=[{"field": key, "filter": True} for key in rows[0]]
                        if rows
                        else [],
                        dashGridOptions={"pagination": True, "paginationPageSize": 15},
                    ),
                ]
            )
        return blocks, ""

    return app


app = create_app()


def main() -> None:
    """Run the corpus dashboard development server."""
    app.run(debug=True)


if __name__ == "__main__":
    main()
