"""SOLID / architecture analysis — available in RunOwl Team and above.

Stub in the public (free) distribution. Install ``runowl-paid`` to enable.
"""

from __future__ import annotations

from architecture.models import ArchReport
from github.models import FileDiff


def run_solid_scan(diffs: list[FileDiff]) -> ArchReport:  # noqa: ARG001
    """Stub — SOLID analysis requires RunOwl Team tier."""
    raise NotImplementedError(
        "Architecture analysis requires RunOwl Team tier. "
        "See https://runowl.ai/pricing to upgrade."
    )
