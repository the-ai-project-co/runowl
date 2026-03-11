"""Deep security scanner — available in RunOwl Team and above.

This module is a stub in the public (free) distribution.
Install the ``runowl-paid`` package to unlock deep OWASP analysis.
"""
from __future__ import annotations

from github.models import FileDiff
from security.models import SecurityReport


def run_deep_scan(diffs: list[FileDiff]) -> SecurityReport:  # noqa: ARG001
    """Stub — deep scan requires RunOwl Team tier."""
    raise NotImplementedError(
        "Deep security analysis requires RunOwl Team tier. "
        "See https://runowl.ai/pricing to upgrade."
    )
