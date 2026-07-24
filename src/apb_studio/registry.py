"""Load the stage registry shared by target expansion and the dashboard."""

from pathlib import Path
from typing import Any

import yaml

REGISTRY_PATH = Path(__file__).resolve().parent / "config" / "registry.yaml"


def load_registry(path: Path | str = REGISTRY_PATH) -> list[dict[str, Any]]:
    """Return the ordered list of stage definitions from the registry YAML."""
    return yaml.safe_load(Path(path).read_text())["stages"]
