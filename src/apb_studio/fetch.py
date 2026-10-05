"""Resumable HTTP downloads shared by every fixture source."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests
from loguru import logger

# Connect and read timeouts for every request. Without a read timeout a server that
# accepts the connection and then stops sending hangs the download forever: the socket
# stays ESTABLISHED, no bytes arrive, and nothing on screen ever changes. The read
# timeout applies per chunk, so a stalled transfer fails instead of waiting out the night.
REQUEST_TIMEOUT = (10, 120)

# A stalled transfer costs an attempt, not the whole file: the bytes already on disk stay
# in a ``.part`` file and the next attempt asks for the rest with a Range header. The
# datasets server answers 206, so a 36 MB archive that died at 69% resumes there.
DOWNLOAD_ATTEMPTS = 5
FIRST_RETRY_SECONDS = 2.0
MAX_RETRY_SECONDS = 30.0
CHUNK_BYTES = 1 << 20

type Check = Callable[[Path], None]
"""Raise ``OSError`` when a finished ``.part`` file holds the wrong bytes."""


def _accept(part: Path, destination: Path, check: Check) -> Path:
    """Move a finished download into place once its bytes pass ``check``."""
    if not part.is_file():
        raise OSError(f"nothing downloaded: {part.name}")
    check(part)
    return part.replace(destination)


def _expected_total(response: Any, resumed_from: int) -> int | None:
    """Read the file's full length from a response, ``None`` when it says nothing."""
    content_range = response.headers.get("Content-Range", "")
    if "/" in content_range:
        total = content_range.rsplit("/", 1)[1].strip()
        return int(total) if total.isdigit() else None
    length = response.headers.get("Content-Length", "")
    return resumed_from + int(length) if length.isdigit() else None


def _is_permanent(error: Exception) -> bool:
    """Say whether retrying an HTTP failure could ever help."""
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    return isinstance(status, int) and 400 <= status < 500 and status not in {408, 429}


def fetch_file(
    url: str, destination: Path, check: Check, attempts: int = DOWNLOAD_ATTEMPTS
) -> Path:
    """Download one file, resuming a partial file and retrying a stalled transfer.

    Bytes accumulate in ``<destination>.part`` so an interrupted transfer is never mistaken
    for a complete file. Each attempt asks for the remainder with a ``Range`` header; a
    server that ignores it answers 200 and the file restarts. The file moves into place
    only once its length matches what the server reports and ``check`` accepts it: a remote
    file replaced between two attempts would otherwise leave two halves spliced together.
    A ``check`` that rejects the bytes deletes the ``.part`` file, so the next attempt
    starts over.

    A 4xx other than 408 or 429 is raised at once — no amount of waiting fixes a URL that
    is not there.
    """
    part = destination.with_name(destination.name + ".part")
    destination.unlink(missing_ok=True)
    delay = FIRST_RETRY_SECONDS
    for attempt in range(1, attempts + 1):
        resumed_from = part.stat().st_size if part.is_file() else 0
        headers = {"Range": f"bytes={resumed_from}-"} if resumed_from else {}
        logger.info(
            "downloading: {}{}",
            url,
            f" (resuming at {resumed_from} bytes)" if resumed_from else "",
        )
        try:
            with requests.get(
                url, stream=True, timeout=REQUEST_TIMEOUT, headers=headers
            ) as response:
                if response.status_code == 416:
                    # Nothing left to send — but only believe that if what is on disk is
                    # the length the server names. A shrunken remote file lands here too.
                    total = _expected_total(response, 0)
                    if resumed_from and total in {None, resumed_from}:
                        logger.info("server reports nothing left to send: {}", part.name)
                        return _accept(part, destination, check)
                    logger.warning("range refused for {} bytes; restarting", resumed_from)
                    part.unlink(missing_ok=True)
                    raise OSError(f"range refused: {resumed_from} bytes on disk, {total} remote")
                if resumed_from and response.status_code != 206:
                    logger.warning("server ignored the range request; restarting {}", part.name)
                    resumed_from = 0
                response.raise_for_status()
                total = _expected_total(response, resumed_from)
                with part.open("ab" if resumed_from else "wb") as handle:
                    for data in response.iter_content(CHUNK_BYTES):
                        handle.write(data)
            size = part.stat().st_size
            if total is not None and size != total:
                raise OSError(f"incomplete download: {size} of {total} bytes")
            return _accept(part, destination, check)
        except (requests.RequestException, OSError) as error:
            if _is_permanent(error):
                raise
            if attempt == attempts:
                raise
            logger.warning(
                "attempt {}/{} failed ({}); retrying in {:.0f}s", attempt, attempts, error, delay
            )
            time.sleep(delay)
            delay = min(delay * 2, MAX_RETRY_SECONDS)
    raise OSError(f"could not download {url}")  # pragma: no cover - the loop returns or raises
