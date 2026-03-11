"""Tests for the Deno sandbox runner."""

from __future__ import annotations

import shutil
from unittest.mock import patch

import pytest

from sandbox.limits import ALLOWED_TOOLS, MAX_ITERATIONS, MAX_LLM_CALLS
from sandbox.runner import (
    ExecutionResult,
    _extract_tool_calls,
    _parse_tool_calls,
    build_deno_command,
    run_in_sandbox,
    validate_tool_call,
)

deno_available = shutil.which("deno") is not None
requires_deno = pytest.mark.skipif(not deno_available, reason="Deno not installed")

# ── Unit tests (no Deno required) ─────────────────────────────────────────────


class TestLimits:
    def test_allowed_tools_set(self) -> None:
        assert "SEARCH_CODE" in ALLOWED_TOOLS
        assert "FETCH_FILE" in ALLOWED_TOOLS
        assert "LIST_DIR" in ALLOWED_TOOLS

    def test_disallowed_tools_not_in_set(self) -> None:
        assert "EXEC" not in ALLOWED_TOOLS
        assert "SHELL" not in ALLOWED_TOOLS
        assert "READ_FILE" not in ALLOWED_TOOLS
        assert "WRITE_FILE" not in ALLOWED_TOOLS

    def test_iteration_limits_positive(self) -> None:
        assert MAX_ITERATIONS > 0
        assert MAX_LLM_CALLS > 0


class TestValidateToolCall:
    def test_allowed_tools_pass(self) -> None:
        for tool in ALLOWED_TOOLS:
            validate_tool_call(tool)  # should not raise

    def test_disallowed_tool_raises(self) -> None:
        with pytest.raises(ValueError, match="not allowed"):
            validate_tool_call("EXEC")

    def test_shell_raises(self) -> None:
        with pytest.raises(ValueError, match="not allowed"):
            validate_tool_call("SHELL")

    def test_unknown_tool_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_tool_call("UNKNOWN_TOOL")


class TestBuildDenoCommand:
    def test_command_starts_with_deno(self) -> None:
        with patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno"):
            cmd = build_deno_command("/tmp/bootstrap.ts", "{}")
        assert cmd[0].endswith("deno")

    def test_run_subcommand_present(self) -> None:
        with patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno"):
            cmd = build_deno_command("/tmp/bootstrap.ts", "{}")
        assert "run" in cmd

    def test_no_network_permission(self) -> None:
        with patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno"):
            cmd = build_deno_command("/tmp/bootstrap.ts", "{}")
        combined = " ".join(cmd)
        assert "--allow-net" not in combined

    def test_no_write_permission(self) -> None:
        with patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno"):
            cmd = build_deno_command("/tmp/bootstrap.ts", "{}")
        combined = " ".join(cmd)
        assert "--allow-write" not in combined

    def test_no_prompt_flag_present(self) -> None:
        with patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno"):
            cmd = build_deno_command("/tmp/bootstrap.ts", "{}")
        assert "--no-prompt" in cmd

    def test_allow_read_scoped(self) -> None:
        with patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno"):
            cmd = build_deno_command("/tmp/bootstrap.ts", "{}")
        read_flags = [f for f in cmd if f.startswith("--allow-read=")]
        assert len(read_flags) == 1
        assert "/tmp" in read_flags[0]


class TestExtractToolCalls:
    def test_finds_allowed_tool(self) -> None:
        code = "result = FETCH_FILE('src/main.py')"
        found = _extract_tool_calls(code)
        assert "FETCH_FILE" in found

    def test_finds_disallowed_tool(self) -> None:
        code = "SHELL('rm -rf /')"
        found = _extract_tool_calls(code)
        assert "SHELL" in found

    def test_empty_code_returns_empty(self) -> None:
        assert _extract_tool_calls("x = 1 + 2") == []


class TestParseToolCalls:
    def test_parses_valid_tool_call_line(self) -> None:
        stdout = (
            'TOOL_CALL:{"tool":"FETCH_FILE","args":{"path":"main.py"},"result":null,"error":null}'
        )
        calls = _parse_tool_calls(stdout)
        assert len(calls) == 1
        assert calls[0]["tool"] == "FETCH_FILE"

    def test_ignores_non_tool_lines(self) -> None:
        stdout = "Some regular output\nAnother line"
        assert _parse_tool_calls(stdout) == []

    def test_handles_malformed_json_gracefully(self) -> None:
        stdout = "TOOL_CALL:not-valid-json"
        calls = _parse_tool_calls(stdout)
        assert calls == []

    def test_parses_multiple_calls(self) -> None:
        stdout = (
            'TOOL_CALL:{"tool":"FETCH_FILE","args":{},"result":null,"error":null}\n'
            'TOOL_CALL:{"tool":"LIST_DIR","args":{},"result":null,"error":null}\n'
        )
        calls = _parse_tool_calls(stdout)
        assert len(calls) == 2


class TestExecutionResultProperties:
    def test_success_true_on_zero_exit(self) -> None:
        r = ExecutionResult(stdout="ok", stderr="", exit_code=0)
        assert r.success is True

    def test_success_false_on_nonzero_exit(self) -> None:
        r = ExecutionResult(stdout="", stderr="err", exit_code=1)
        assert r.success is False

    def test_success_false_on_timeout(self) -> None:
        r = ExecutionResult(stdout="", stderr="", exit_code=0, timed_out=True)
        assert r.success is False


# ── Integration tests (requires Deno) ─────────────────────────────────────────


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
