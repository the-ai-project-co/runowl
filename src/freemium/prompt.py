"""Upgrade prompt formatters — CLI and markdown output for gated features."""

from __future__ import annotations

from freemium.gate import FeatureGatedError
from freemium.models import GateResult


def format_upgrade_prompt_cli(result: GateResult) -> str:
    """Return a Rich-formatted upgrade prompt for terminal output."""
    lines = [
        "[bold yellow]⚠ Feature not available on your current plan[/]",
        "",
        f"  [dim]{result.upgrade_message}[/]",
        "",
        f"  Upgrade at: [link={result.upgrade_url}]{result.upgrade_url}[/link]",
    ]
    return "\n".join(lines)


def format_upgrade_prompt_markdown(result: GateResult) -> str:
    """Return a markdown upgrade prompt for PR comments or API responses."""
    lines = [
        "---",
        "### ⚡ RunOwl — Upgrade Required",
        "",
        f"> {result.upgrade_message}",
        "",
        f"[Upgrade to {result.required_tier.title()} plan]({result.upgrade_url})",
        "---",
    ]
    return "\n".join(lines)


def format_gated_error_cli(exc: FeatureGatedError) -> str:
    """Convenience wrapper for FeatureGatedError → CLI prompt."""
    return format_upgrade_prompt_cli(exc.result)


def format_gated_error_markdown(exc: FeatureGatedError) -> str:
    """Convenience wrapper for FeatureGatedError → markdown prompt."""
    return format_upgrade_prompt_markdown(exc.result)
