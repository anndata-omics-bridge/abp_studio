"""Vendor naming shared by the concrete corpus workflows."""

from __future__ import annotations

import re

# ProteoBench's names for software APB2 names otherwise: WOMBAT-P as its publication does.
_APB2_NAMES = {"WOMBAT": "WOMBAT-P"}


def parameter_software(software_name: str, /) -> str:
    """Select the parameter grammar; compound FragPipe/DIA-NN names use their catalog prefix."""
    name = _APB2_NAMES.get(software_name, software_name)
    return re.sub(r"[^a-z0-9]", "", name.split("(", 1)[0].strip().lower())


def result_software(software_name: str) -> str:
    """Identify the result-producing software when no parameter grammar is needed."""
    return {
        "FragPipe (DIA-NN quant)": "diann",
    }.get(software_name, parameter_software(software_name))
