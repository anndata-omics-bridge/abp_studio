"""Build and inspect APB Studio without installing from PyPI."""

from __future__ import annotations

import configparser
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

_ENTRY_POINTS = {
    "apb-studio": "apb_studio.dashboard:main",
    "apb-studio-corpus-runner": "apb_studio.dashboard:main",
    "apb-studio-fixture-manager": "apb_studio.testdata_app:main",
    "apb-studio-testdata": "apb_studio.testdata_app:main",
}
_REQUIRED_FILES = {
    "apb_studio/__init__.py",
    "apb_studio/py.typed",
    "apb_studio/config/registry.yaml",
    "apb_studio/workflow/Snakefile",
}
_INSTALLED_CHECK = """
import os
from pathlib import Path

import apb_studio
from apb_studio.execution import SNAKEFILE
from apb_studio.registry import REGISTRY_PATH, load_registry
from apb_studio.settings import DEFAULT_OUTPUT_ROOT, DEFAULT_TEST_DATA_ROOT

installed_root = Path(os.environ["APB_STUDIO_SMOKE_ROOT"]).resolve()
package_root = Path(apb_studio.__file__).resolve().parent
if not package_root.is_relative_to(installed_root):
    raise RuntimeError(f"Imported APB Studio outside smoke install: {package_root}")
if not REGISTRY_PATH.is_file() or not load_registry():
    raise RuntimeError(f"Installed registry is unavailable: {REGISTRY_PATH}")
if not SNAKEFILE.is_file():
    raise RuntimeError(f"Installed Snakefile is unavailable: {SNAKEFILE}")
for default_root in (DEFAULT_TEST_DATA_ROOT, DEFAULT_OUTPUT_ROOT):
    if package_root in default_root.parents:
        raise RuntimeError(f"Default path points inside the installed package: {default_root}")
"""


def _verify_wheel(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        if missing := _REQUIRED_FILES - names:
            raise RuntimeError(f"Wheel is missing package files: {sorted(missing)}")

        entry_point_files = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
        if len(entry_point_files) != 1:
            raise RuntimeError(f"Expected one entry_points.txt, found {entry_point_files}")

        parser = configparser.ConfigParser()
        parser.read_string(archive.read(entry_point_files[0]).decode())
        console_scripts = parser["console_scripts"]
        for name, expected in _ENTRY_POINTS.items():
            actual = console_scripts.get(name)
            if actual != expected:
                raise RuntimeError(f"Unexpected {name} entry point: {actual!r}")


def _verify_installed_wheel(wheel: Path, install_root: Path) -> None:
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--target",
            str(install_root),
            "--no-deps",
            str(wheel),
        ],
        check=True,
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(install_root)
    environment["APB_STUDIO_SMOKE_ROOT"] = str(install_root)
    subprocess.run(
        [sys.executable, "-c", _INSTALLED_CHECK],
        check=True,
        cwd=install_root,
        env=environment,
    )


def main() -> None:
    """Build, inspect, install, and import the wheel's public contract."""
    with tempfile.TemporaryDirectory(prefix="apb-studio-package-") as temp_dir:
        output_dir = Path(temp_dir)
        subprocess.run(["uv", "build", "--out-dir", str(output_dir)], check=True)
        wheels = list(output_dir.glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"Expected one wheel, found {wheels}")
        _verify_wheel(wheels[0])
        _verify_installed_wheel(wheels[0], output_dir / "installed")
        print(f"Package smoke passed: {wheels[0].name}")


if __name__ == "__main__":
    main()
