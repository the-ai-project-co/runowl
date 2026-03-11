"""Test result storage, aggregation, and GitHub PR comment formatting."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from testing.models import TestResult, TestStatus, TestSuite

logger = logging.getLogger(__name__)

_STORE_ROOT = Path.home() / ".runowl" / "test_results"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_suite(suite: TestSuite) -> Path:
    """Persist a TestSuite to disk as JSON. Returns the saved file path."""
    _STORE_ROOT.mkdir(parents=True, exist_ok=True)
    dest = _STORE_ROOT / f"{suite.id}.json"
    dest.write_text(json.dumps(_suite_to_dict(suite), indent=2), encoding="utf-8")
    logger.debug("Saved test suite: %s", dest)
    return dest


def load_suite(suite_id: str) -> TestSuite | None:
    """Load a TestSuite from disk by ID. Returns None if not found."""
    path = _STORE_ROOT / f"{suite_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _suite_from_dict(data)
    except Exception as exc:
        logger.warning("Failed to load suite %s: %s", suite_id, exc)
        return None


# ---------------------------------------------------------------------------
# GitHub PR comment formatting
# ---------------------------------------------------------------------------

_STATUS_EMOJI = {
    TestStatus.PASS: "✅",
    TestStatus.FAIL: "❌",
    TestStatus.ERROR: "⚠️",
    TestStatus.SKIP: "⏭️",
    TestStatus.TIMEOUT: "⏱️",
}


def format_results_markdown(suite: TestSuite) -> str:
    """Render a GitHub PR comment body for the test suite results."""
    lines: list[str] = []

    # Header
    if suite.all_passed:
        lines.append("## ✅ RunOwl Tests — All Passed")
    elif suite.has_failures:
        lines.append("## ❌ RunOwl Tests — Failures Detected")
    else:
        lines.append("## ⏭️ RunOwl Tests — No Results")

    lines.append("")

    # Summary row
    lines.append(
        f"**{suite.passed} passed** · "
        f"**{suite.failed} failed** · "
        f"**{suite.errors} errors** · "
        f"**{suite.skipped} skipped** · "
        f"framework: `{suite.framework}`"
    )
    lines.append("")

    if not suite.results:
        if not suite.generation_success:
            lines.append(
                f"> ⚠️ Test generation failed: "
                f"{suite.generation_error or 'no test cases were produced'}"
            )
        return "\n".join(lines)

    # Results table
    lines.append("| Status | Test | Duration |")
    lines.append("|---|---|---|")
    for result in suite.results:
        emoji = _STATUS_EMOJI.get(result.status, "?")
        duration = f"{result.duration_ms:.0f} ms" if result.duration_ms else "—"
        name = result.test_name or result.test_id
        lines.append(f"| {emoji} {result.status} | `{name}` | {duration} |")

    lines.append("")

    # Failure details
    failures = [r for r in suite.results if r.failed]
    if failures:
        lines.append("<details>")
        lines.append("<summary>Failure details</summary>")
        lines.append("")
        for result in failures:
            lines.append(f"### ❌ `{result.test_name}`")
            if result.error_message:
                lines.append(f"```\n{result.error_message[:1000]}\n```")
            elif result.stderr:
                lines.append(f"```\n{result.stderr[:500]}\n```")
            if result.video_path:
                lines.append(f"📹 [Video recording]({result.video_path})")
            if result.replay_path:
                lines.append(f"🎬 [Session trace]({result.replay_path})")
            lines.append("")
        lines.append("</details>")

    return "\n".join(lines)


def format_results_json(suite: TestSuite) -> dict:
    """Structured JSON output for CI/CD pipelines."""
    return {
        "suite_id": suite.id,
        "pr_ref": suite.pr_ref,
        "framework": suite.framework,
        "summary": suite.to_summary(),
        "results": [
            {
                "test_id": r.test_id,
                "test_name": r.test_name,
                "status": r.status,
                "duration_ms": r.duration_ms,
                "error_message": r.error_message,
                "video_path": r.video_path,
                "replay_path": r.replay_path,
            }
            for r in suite.results
        ],
        "generation_success": suite.generation_success,
        "generation_error": suite.generation_error,
    }


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _suite_to_dict(suite: TestSuite) -> dict:
    return {
        "id": suite.id,
        "pr_ref": suite.pr_ref,
        "framework": suite.framework,
        "generation_success": suite.generation_success,
        "generation_error": suite.generation_error,
        "results": [
            {
                "test_id": r.test_id,
                "test_name": r.test_name,
                "status": r.status,
                "duration_ms": r.duration_ms,
                "stdout": r.stdout,
                "stderr": r.stderr,
                "error_message": r.error_message,
                "video_path": r.video_path,
                "replay_path": r.replay_path,
                "screenshots": r.screenshots,
                "executed_at": r.executed_at.isoformat(),
            }
            for r in suite.results
        ],
    }


def _suite_from_dict(data: dict) -> TestSuite:
    from datetime import datetime

    from testing.models import FrameworkType

    suite = TestSuite(
        id=data["id"],
        pr_ref=data["pr_ref"],
        framework=FrameworkType(data["framework"]),
        generation_success=data.get("generation_success", False),
        generation_error=data.get("generation_error"),
    )
    for r in data.get("results", []):
        suite.results.append(
            TestResult(
                test_id=r["test_id"],
                test_name=r["test_name"],
                status=TestStatus(r["status"]),
                duration_ms=r.get("duration_ms", 0.0),
                stdout=r.get("stdout", ""),
                stderr=r.get("stderr", ""),
                error_message=r.get("error_message", ""),
                video_path=r.get("video_path"),
                replay_path=r.get("replay_path"),
                screenshots=r.get("screenshots", []),
                executed_at=datetime.fromisoformat(r["executed_at"]),
            )
        )
    return suite
