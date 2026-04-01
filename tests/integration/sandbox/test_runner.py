"""Integration tests for the Deno sandbox runner (requires Deno installed)."""

from __future__ import annotations

import shutil

import pytest

from sandbox.runner import run_in_sandbox

deno_available = shutil.which("deno") is not None
requires_deno = pytest.mark.skipif(not deno_available, reason="Deno not installed")


@requires_deno
class TestRunInSandbox:
    async def test_disallowed_tool_blocked_before_execution(self) -> None:
        """SHELL tool should be caught by pre-flight validation."""
        with pytest.raises(ValueError, match="not allowed"):
            await run_in_sandbox("SHELL('echo hi')", {})

    async def test_allowed_tool_dispatched(self) -> None:
        """FETCH_FILE in code should pass pre-flight and run."""
        result = await run_in_sandbox(
            "const r = FETCH_FILE('src/main.py'); console.log('done');",
            {"owner": "test", "repo": "test", "pr": 1},
        )
        # Sandbox ran (exit 0 or tool call recorded)
        assert not result.timed_out
        assert len(result.tool_calls) >= 1
        assert result.tool_calls[0]["tool"] == "FETCH_FILE"

    async def test_timeout_respected(self) -> None:
        """A script that sleeps forever should time out."""
        # Use Atomics.wait to block without burning CPU — reliably triggers timeout
        code = "Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 999999);"
        result = await run_in_sandbox(code, {}, timeout=2)
        assert result.timed_out
        assert result.success is False
