"""Architecture check definitions — stub in the public distribution.

Full implementation available in RunOwl Team tier (runowl-paid).
"""

from __future__ import annotations

from architecture.models import ArchFinding, ArchReport  # noqa: F401
from github.models import FileDiff

ARCH_CHECKS: list[object] = []

_STUB_MSG = (
    "Architecture analysis requires RunOwl Team tier. " "See https://runowl.ai/pricing to upgrade."
)


def _stub(diffs: list[FileDiff]) -> list[ArchFinding]:  # noqa: ARG001
    raise NotImplementedError(_STUB_MSG)


def check_single_responsibility(diffs: list[FileDiff]) -> list[ArchFinding]:
    return _stub(diffs)


def check_open_closed(diffs: list[FileDiff]) -> list[ArchFinding]:
    return _stub(diffs)


def check_liskov_substitution(diffs: list[FileDiff]) -> list[ArchFinding]:
    return _stub(diffs)


def check_interface_segregation(diffs: list[FileDiff]) -> list[ArchFinding]:
    return _stub(diffs)


def check_dependency_inversion(diffs: list[FileDiff]) -> list[ArchFinding]:
    return _stub(diffs)


def check_long_methods(diffs: list[FileDiff]) -> list[ArchFinding]:
    return _stub(diffs)


def check_deep_nesting(diffs: list[FileDiff]) -> list[ArchFinding]:
    return _stub(diffs)


def check_feature_envy(diffs: list[FileDiff]) -> list[ArchFinding]:
    return _stub(diffs)
