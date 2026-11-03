"""Show apb-catalog's bundle: its stored tables, its answers and the software versions APB2 supports.

The viewer reads the bundle through apb-catalog-ts and computes nothing on the server: `view`
serves the viewer at / and the bundle at /data/ as files, and `publish` writes the same layout.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter
from loguru import logger

from apb_studio.catalog_viewer.publish import publish_site, require_bundle
from apb_studio.fixture_store import Store
from apb_studio.fixture_viewer.server import run
from apb_studio.settings import load_settings

WEB_ROOT = Path(__file__).parent / "web"
VIEWER_PORT = 8767

app = App(name="catalog", help=__doc__, help_on_error=True)


def default_bundle() -> Path:
    """apb-catalog's ``make bundle`` output, beside the Studio checkout that holds the test data."""
    workspace = load_settings().test_data_root.parent.parent
    return workspace / "apb-catalog" / "build" / "apb-catalog-bundle"


def _bundle(bundle: Path | None) -> Path:
    """Return the bundle folder given, or the default one, once it holds a bundle."""
    try:
        return require_bundle((bundle if bundle is not None else default_bundle()).resolve())
    except ValueError as error:
        raise SystemExit(str(error)) from None


@app.command
def view(*, bundle: Path | None = None, host: str = "127.0.0.1", port: int = VIEWER_PORT) -> None:
    """Serve the catalog viewer on one bundle until interrupted.

    Args:
        bundle: The bundle folder; defaults to apb-catalog's ``make bundle`` output.
        host: The interface to bind.
        port: The port to bind.
    """
    run(Store(root=_bundle(bundle)), host=host, port=port, web_root=WEB_ROOT)


@app.command
def publish(
    site: Annotated[Path, Parameter(help="Empty folder for the viewer and its bundle")],
    /,
    *,
    bundle: Annotated[
        Path | None,
        Parameter(help="The bundle folder; defaults to apb-catalog's make bundle output"),
    ] = None,
) -> None:
    """Copy the catalog viewer into SITE and the bundle into SITE/data for a plain file server."""
    try:
        publish_site(_bundle(bundle), WEB_ROOT, site.resolve())
    except ValueError as error:
        raise SystemExit(str(error)) from None
    logger.info("Published the catalog viewer to {}", site)


def main() -> None:
    """Run the catalog viewer command-line application."""
    logger.remove()
    logger.add(sys.stderr, format="<level>{level: <7}</level> | {message}", level="INFO")
    app()
