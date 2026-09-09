"""Run a selected concrete Python workflow over the corpus."""

from cyclopts import App

from apb_studio.corpus.cli import run

app = App()
app.default(run)

if __name__ == "__main__":
    app()
