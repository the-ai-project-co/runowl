"""Deep security check stubs — full implementation in RunOwl Team tier (runowl-paid)."""

from __future__ import annotations

from github.models import FileDiff
from security.models import SecurityHit

DEEP_CHECKS: list[object] = []

_STUB_MSG = (
    "Deep security analysis requires RunOwl Team tier. " "See https://runowl.ai/pricing to upgrade."
)


def _stub(diffs: list[FileDiff]) -> list[SecurityHit]:  # noqa: ARG001
    raise NotImplementedError(_STUB_MSG)


def check_injection(diffs: list[FileDiff]) -> list[SecurityHit]:
    return _stub(diffs)


def check_broken_access_control(diffs: list[FileDiff]) -> list[SecurityHit]:
    return _stub(diffs)


def check_cryptographic_failures(diffs: list[FileDiff]) -> list[SecurityHit]:
    return _stub(diffs)


def check_security_misconfiguration(diffs: list[FileDiff]) -> list[SecurityHit]:
    return _stub(diffs)


def check_supply_chain(diffs: list[FileDiff]) -> list[SecurityHit]:
    return _stub(diffs)


def check_race_conditions(diffs: list[FileDiff]) -> list[SecurityHit]:
    return _stub(diffs)


def check_jwt_auth(diffs: list[FileDiff]) -> list[SecurityHit]:
    return _stub(diffs)
