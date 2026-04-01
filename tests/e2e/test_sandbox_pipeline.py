"""E2E tests for the sandbox security model.

No Deno installation required — these tests verify the security constraints,
command construction, tool validation, and parsing logic without actually
executing a Deno process.
"""

from unittest.mock import patch

import pytest

from sandbox.limits import (
    ALLOWED_TOOLS,
    EXECUTION_TIMEOUT,
    MAX_ITERATIONS,
    MAX_LLM_CALLS,
    MAX_OUTPUT_BYTES,
)
from sandbox.runner import (
    ExecutionResult,
    _extract_tool_calls,
    _parse_tool_calls,
    build_deno_command,
    validate_tool_call,
)


# ---------------------------------------------------------------------------
# 1. Full security audit of Deno command
# ---------------------------------------------------------------------------


class TestDenoCommandSecurity:
    """Verify that build_deno_command produces a strictly sandboxed command."""

    @patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno")
    def test_no_network_permission(self, _mock_deno):
        cmd = build_deno_command("/sandbox/bootstrap.ts", "{}")
        cmd_str = " ".join(cmd)
        assert "--allow-net" not in cmd_str

    @patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno")
    def test_no_write_permission(self, _mock_deno):
        cmd = build_deno_command("/sandbox/bootstrap.ts", "{}")
        cmd_str = " ".join(cmd)
        assert "--allow-write" not in cmd_str

    @patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno")
    def test_no_subprocess_permission(self, _mock_deno):
        cmd = build_deno_command("/sandbox/bootstrap.ts", "{}")
        cmd_str = " ".join(cmd)
        assert "--allow-run" not in cmd_str

    @patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno")
    def test_no_ffi_permission(self, _mock_deno):
        cmd = build_deno_command("/sandbox/bootstrap.ts", "{}")
        cmd_str = " ".join(cmd)
        assert "--allow-ffi" not in cmd_str

    @patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno")
    def test_no_hrtime_permission(self, _mock_deno):
        cmd = build_deno_command("/sandbox/bootstrap.ts", "{}")
        cmd_str = " ".join(cmd)
        assert "--allow-hrtime" not in cmd_str

    @patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno")
    def test_read_is_scoped(self, _mock_deno):
        """Read permission should be scoped to the script's directory only."""
        cmd = build_deno_command("/sandbox/bootstrap.ts", "{}")
        # Find the --allow-read flag
        read_flags = [c for c in cmd if c.startswith("--allow-read")]
        assert len(read_flags) == 1
        flag = read_flags[0]
        # Must be scoped (--allow-read=<dir>), not unscoped (--allow-read)
        assert "=" in flag
        assert "/sandbox" in flag

    @patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno")
    def test_no_prompt_flag_present(self, _mock_deno):
        cmd = build_deno_command("/sandbox/bootstrap.ts", "{}")
        assert "--no-prompt" in cmd

    @patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno")
    def test_command_starts_with_deno_run(self, _mock_deno):
        cmd = build_deno_command("/sandbox/bootstrap.ts", "{}")
        assert cmd[0] == "/usr/local/bin/deno"
        assert cmd[1] == "run"

    @patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno")
    def test_script_path_is_last_argument(self, _mock_deno):
        cmd = build_deno_command("/sandbox/bootstrap.ts", "{}")
        assert cmd[-1] == "/sandbox/bootstrap.ts"

    @patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno")
    def test_env_permission_is_scoped(self, _mock_deno):
        cmd = build_deno_command("/sandbox/bootstrap.ts", "{}")
        env_flags = [c for c in cmd if c.startswith("--allow-env")]
        assert len(env_flags) == 1
        flag = env_flags[0]
        assert "=" in flag  # scoped, not blanket --allow-env
        assert "RUNOWL_CONTEXT" in flag


# ---------------------------------------------------------------------------
# 2. Tool validation — allowed and disallowed tools
# ---------------------------------------------------------------------------


class TestToolValidation:
    def test_all_allowed_tools_pass(self):
        for tool in ALLOWED_TOOLS:
            # Should not raise
            validate_tool_call(tool)

    def test_disallowed_tools_rejected(self):
        disallowed = [
            "READ_FILE",
            "WRITE_FILE",
            "EXEC",
            "SHELL",
            "DELETE",
            "NETWORK",
            "HTTP_REQUEST",
            "os.system",
            "subprocess.run",
            "eval",
            "exec",
            "open",
            "import",
            "",
        ]
        for tool in disallowed:
            with pytest.raises(ValueError, match="not allowed"):
                validate_tool_call(tool)

    def test_case_sensitivity(self):
        """Tool names are case-sensitive — lowercase versions must be rejected."""
        for tool in ALLOWED_TOOLS:
            lower = tool.lower()
            if lower != tool:  # only test if case differs
                with pytest.raises(ValueError, match="not allowed"):
                    validate_tool_call(lower)

    def test_error_message_lists_allowed_tools(self):
        with pytest.raises(ValueError, match="Allowed tools") as exc_info:
            validate_tool_call("FORBIDDEN_TOOL")
        error_msg = str(exc_info.value)
        for tool in ALLOWED_TOOLS:
            assert tool in error_msg


# ---------------------------------------------------------------------------
# 3. Tool extraction from code strings
# ---------------------------------------------------------------------------


class TestExtractToolCalls:
    def test_finds_allowed_tool(self):
        code = 'result = SEARCH_CODE("query")'
        found = _extract_tool_calls(code)
        assert "SEARCH_CODE" in found

    def test_finds_multiple_allowed_tools(self):
        code = """
result = SEARCH_CODE("find something")
file = FETCH_FILE("src/main.py")
entries = LIST_DIR("src/")
"""
        found = _extract_tool_calls(code)
        assert "SEARCH_CODE" in found
        assert "FETCH_FILE" in found
        assert "LIST_DIR" in found

    def test_finds_disallowed_tools(self):
        code = 'EXEC("rm -rf /")'
        found = _extract_tool_calls(code)
        assert "EXEC" in found

    def test_finds_write_file_disallowed(self):
        code = 'WRITE_FILE("exploit.py", payload)'
        found = _extract_tool_calls(code)
        assert "WRITE_FILE" in found

    def test_mixed_allowed_and_disallowed(self):
        code = """
data = SEARCH_CODE("pattern")
SHELL("whoami")
file = FETCH_FILE("config.py")
"""
        found = _extract_tool_calls(code)
        assert "SEARCH_CODE" in found
        assert "FETCH_FILE" in found
        assert "SHELL" in found

    def test_no_tools_in_plain_code(self):
        code = """
x = 1 + 2
print(x)
"""
        found = _extract_tool_calls(code)
        assert found == []

    def test_tool_in_string_literal_still_detected(self):
        """Pre-flight check is conservative — references in strings are flagged."""
        code = 'comment = "EXEC should not be used"'
        found = _extract_tool_calls(code)
        assert "EXEC" in found

    def test_run_tests_tool(self):
        code = 'result = RUN_TESTS("test_suite")'
        found = _extract_tool_calls(code)
        assert "RUN_TESTS" in found


# ---------------------------------------------------------------------------
# 4. Tool call parsing from stdout
# ---------------------------------------------------------------------------


class TestParseToolCalls:
    def test_valid_json_tool_call(self):
        stdout = 'TOOL_CALL:{"tool": "SEARCH_CODE", "args": {"query": "def main"}}\n'
        calls = _parse_tool_calls(stdout)
        assert len(calls) == 1
        assert calls[0]["tool"] == "SEARCH_CODE"

    def test_malformed_json_skipped(self):
        stdout = "TOOL_CALL:{invalid json here}\n"
        calls = _parse_tool_calls(stdout)
        assert calls == []

    def test_multiple_tool_calls(self):
        stdout = (
            'TOOL_CALL:{"tool": "SEARCH_CODE", "args": {"query": "auth"}}\n'
            'TOOL_CALL:{"tool": "FETCH_FILE", "args": {"path": "src/auth.py"}}\n'
        )
        calls = _parse_tool_calls(stdout)
        assert len(calls) == 2
        assert calls[0]["tool"] == "SEARCH_CODE"
        assert calls[1]["tool"] == "FETCH_FILE"

    def test_interleaved_with_regular_output(self):
        stdout = (
            "Starting analysis...\n"
            'TOOL_CALL:{"tool": "SEARCH_CODE", "args": {}}\n'
            "Processing results...\n"
            'TOOL_CALL:{"tool": "FETCH_FILE", "args": {}}\n'
            "Done.\n"
        )
        calls = _parse_tool_calls(stdout)
        assert len(calls) == 2

    def test_empty_stdout(self):
        calls = _parse_tool_calls("")
        assert calls == []

    def test_no_tool_call_prefix_lines(self):
        stdout = "Line 1\nLine 2\nLine 3\n"
        calls = _parse_tool_calls(stdout)
        assert calls == []

    def test_partial_prefix_not_matched(self):
        stdout = "TOOL_CAL:{}\nTOOL_CALLS:{}\n"
        calls = _parse_tool_calls(stdout)
        assert calls == []

    def test_tool_call_with_nested_json(self):
        stdout = 'TOOL_CALL:{"tool": "SEARCH_CODE", "args": {"query": "func", "options": {"regex": true}}}\n'
        calls = _parse_tool_calls(stdout)
        assert len(calls) == 1
        assert calls[0]["args"]["options"]["regex"] is True


# ---------------------------------------------------------------------------
# 5. ExecutionResult properties
# ---------------------------------------------------------------------------


class TestExecutionResult:
    def test_success_on_zero_exit_no_timeout(self):
        result = ExecutionResult(stdout="ok", stderr="", exit_code=0)
        assert result.success is True

    def test_failure_on_nonzero_exit(self):
        result = ExecutionResult(stdout="", stderr="error", exit_code=1)
        assert result.success is False

    def test_failure_on_timeout(self):
        result = ExecutionResult(
            stdout="", stderr="timed out", exit_code=-1, timed_out=True
        )
        assert result.success is False

    def test_timeout_overrides_zero_exit(self):
        result = ExecutionResult(
            stdout="", stderr="", exit_code=0, timed_out=True
        )
        assert result.success is False

    def test_truncated_flag(self):
        result = ExecutionResult(
            stdout="truncated...",
            stderr="",
            exit_code=0,
            truncated=True,
        )
        assert result.success is True
        assert result.truncated is True

    def test_default_values(self):
        result = ExecutionResult(stdout="", stderr="", exit_code=0)
        assert result.truncated is False
        assert result.timed_out is False
        assert result.tool_calls == []

    def test_tool_calls_populated(self):
        result = ExecutionResult(
            stdout="",
            stderr="",
            exit_code=0,
            tool_calls=[{"tool": "SEARCH_CODE", "args": {}}],
        )
        assert len(result.tool_calls) == 1


# ---------------------------------------------------------------------------
# 6. Limits are sane
# ---------------------------------------------------------------------------


class TestLimitsSanity:
    def test_max_iterations_positive(self):
        assert MAX_ITERATIONS > 0

    def test_max_llm_calls_positive(self):
        assert MAX_LLM_CALLS > 0

    def test_execution_timeout_positive(self):
        assert EXECUTION_TIMEOUT > 0

    def test_max_output_bytes_positive(self):
        assert MAX_OUTPUT_BYTES > 0

    def test_allowed_tools_is_nonempty(self):
        assert len(ALLOWED_TOOLS) > 0

    def test_allowed_tools_is_frozenset(self):
        assert isinstance(ALLOWED_TOOLS, frozenset)

    def test_timeout_is_reasonable(self):
        """Timeout should be between 10 seconds and 10 minutes."""
        assert 10 <= EXECUTION_TIMEOUT <= 600

    def test_max_output_bytes_at_least_64kb(self):
        assert MAX_OUTPUT_BYTES >= 64 * 1024

    def test_expected_tools_present(self):
        assert "SEARCH_CODE" in ALLOWED_TOOLS
        assert "FETCH_FILE" in ALLOWED_TOOLS
        assert "LIST_DIR" in ALLOWED_TOOLS


# ---------------------------------------------------------------------------
# 7. Command building with different script paths and contexts
# ---------------------------------------------------------------------------


class TestCommandBuildingVariations:
    @patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno")
    def test_nested_script_path(self, _mock_deno):
        cmd = build_deno_command("/opt/runowl/sandbox/scripts/bootstrap.ts", "{}")
        assert cmd[-1] == "/opt/runowl/sandbox/scripts/bootstrap.ts"
        read_flag = [c for c in cmd if c.startswith("--allow-read=")][0]
        assert "/opt/runowl/sandbox/scripts" in read_flag

    @patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno")
    def test_context_json_not_in_command(self, _mock_deno):
        """Context is passed via env var, NOT as a CLI argument."""
        ctx = '{"pr": {"owner": "test", "repo": "repo"}}'
        cmd = build_deno_command("/sandbox/bootstrap.ts", ctx)
        cmd_str = " ".join(cmd)
        assert ctx not in cmd_str

    @patch("sandbox.runner._deno_bin", return_value="/home/user/.deno/bin/deno")
    def test_custom_deno_path(self, _mock_deno):
        cmd = build_deno_command("/sandbox/bootstrap.ts", "{}")
        assert cmd[0] == "/home/user/.deno/bin/deno"

    @patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno")
    def test_quiet_flag_present(self, _mock_deno):
        cmd = build_deno_command("/sandbox/bootstrap.ts", "{}")
        assert "--quiet" in cmd

    @patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno")
    def test_command_is_list_of_strings(self, _mock_deno):
        cmd = build_deno_command("/sandbox/bootstrap.ts", "{}")
        assert isinstance(cmd, list)
        assert all(isinstance(c, str) for c in cmd)

    @patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno")
    def test_all_required_flags_present(self, _mock_deno):
        cmd = build_deno_command("/sandbox/bootstrap.ts", "{}")
        assert "run" in cmd
        assert "--no-prompt" in cmd
        assert "--quiet" in cmd
        assert any(c.startswith("--allow-read=") for c in cmd)
        assert any(c.startswith("--allow-env=") for c in cmd)

    @patch("sandbox.runner._deno_bin", return_value="/usr/local/bin/deno")
    def test_no_all_permission_flag(self, _mock_deno):
        cmd = build_deno_command("/sandbox/bootstrap.ts", "{}")
        cmd_str = " ".join(cmd)
        assert "--allow-all" not in cmd_str
        assert "-A" not in cmd  # -A is shorthand for --allow-all
