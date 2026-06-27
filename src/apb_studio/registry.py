"""Load the stage registry and the corpus config.

Both the Snakefile and the dashboard read the same registry so the pipeline and the GUI cannot
drift. This module is the dashboard's reader; the Snakefile loads the YAML directly.
"""

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = _REPO_ROOT / "config" / "registry.yaml"


def load_registry(path: Path | str = REGISTRY_PATH) -> list[dict]:
    """Return the ordered list of stage definitions from the registry YAML."""
    return yaml.safe_load(Path(path).read_text())["stages"]


def load_corpus(path: Path | str) -> dict:
    """Return the corpus config (input_root, output_root, modules)."""
    return yaml.safe_load(Path(path).read_text())
