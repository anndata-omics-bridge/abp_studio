"""A local static server for the viewer and the fixture store.

The viewer cannot be opened from ``file://``: browsers refuse ``fetch`` of local
files. This answers ``GET`` and ``HEAD`` from two directories and nothing else.
The routing is :mod:`apb_studio.fixture_viewer.routes`, which is pure; this module
is the socket.
"""

from __future__ import annotations

import errno
import shutil
from collections.abc import Callable
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, override

from loguru import logger

from apb_studio.fixture_store import Store
from apb_studio.fixture_viewer.routes import Response, resolve

WEB_ROOT = Path(__file__).parent / "web"
type Resolver = Callable[[str, Path, Store], Response]


class StoreHandler(BaseHTTPRequestHandler):
    """Serves the viewer and the store from one origin."""

    protocol_version = "HTTP/1.1"
    server_version = "apb-studio-fixture"
    sys_version = ""

    def __init__(
        self,
        *args: Any,
        web_root: Path,
        store: Store,
        resolver: Resolver,
        **kwargs: Any,
    ) -> None:
        self._web_root = web_root
        self._store = store
        self._resolver = resolver
        super().__init__(*args, **kwargs)

    def _respond(self, *, with_body: bool) -> None:
        response = self._resolver(self.path, self._web_root, self._store)
        self.send_response(response.status)
        for name, value in response.headers:
            self.send_header(name, value)
        length = response.file.stat().st_size if response.file else len(response.body)
        self.send_header("Content-Length", str(length))
        self.end_headers()
        if with_body:
            if response.file:
                with response.file.open("rb") as stream:
                    shutil.copyfileobj(stream, self.wfile)
            else:
                self.wfile.write(response.body)

    def do_GET(self) -> None:
        """Answer a ``GET``."""
        self._respond(with_body=True)

    def do_HEAD(self) -> None:
        """Answer a ``HEAD``."""
        self._respond(with_body=False)

    @override
    def log_message(self, format: str, *args: Any) -> None:
        """Keep polling access logs available without printing them during normal use."""
        logger.trace(f"{self.address_string()} {format % args}")


def build_server(
    store: Store,
    host: str,
    port: int,
    web_root: Path = WEB_ROOT,
    resolver: Resolver = resolve,
) -> ThreadingHTTPServer:
    """Create the server without starting it."""
    if not store.root.is_dir():
        raise NotADirectoryError(f"Not a directory: {store.root}")
    handler = partial(StoreHandler, web_root=web_root, store=store, resolver=resolver)
    return ThreadingHTTPServer((host, port), handler)


def run(store: Store, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Serve the viewer until interrupted."""
    try:
        server = build_server(store, host, port)
    except OSError as error:
        if error.errno not in {errno.EADDRINUSE, errno.EACCES}:
            raise
        raise SystemExit(
            f"Cannot bind {host}:{port}: {error.strerror}. "
            "Another viewer is probably already serving; stop it or pass --port."
        ) from error
    bound = server.server_address
    logger.info(f"serving {store.root} at http://{bound[0]}:{bound[1]}/")
    logger.info("press Ctrl-C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("stopped")
    finally:
        server.server_close()
