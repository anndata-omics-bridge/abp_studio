"""Load the stage registry shared by target expansion and the dashboard."""

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = _REPO_ROOT / "config" / "registry.yaml"


def load_registry(path: Path | str = REGISTRY_PATH) -> list[dict]:
    """Return the ordered list of stage definitions from the registry YAML."""
    return yaml.safe_load(Path(path).read_text())["stages"]
