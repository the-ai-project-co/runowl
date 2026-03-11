"""Deno-based sandbox for safe Python code execution during review.

The sandbox:
- Runs a Python script inside `deno run` with strict permission flags.
- Only allows the three whitelisted tool calls: SEARCH_CODE, FETCH_FILE, LIST_DIR.
- Blocks all file I/O (open, os.path, pathlib) and network access inside the script.
- Injects serializable context (PR diff, repo ref, etc.) via stdin as JSON.
- Enforces wall-clock timeout and output size limits.
- Returns structured ExecutionResult with stdout, stderr, exit code, and truncation flag.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from sandbox.limits import ALLOWED_TOOLS, EXECUTION_TIMEOUT, MAX_OUTPUT_BYTES

logger = logging.getLogger(__name__)

# Path to the Deno bootstrap script that wraps the agent code
_BOOTSTRAP = Path(__file__).parent / "bootstrap.ts"


# Deno binary — prefer PATH, fall back to ~/.deno/bin/deno
def _deno_bin() -> str:
    if found := shutil.which("deno"):
        return found
    fallback = Path.home() / ".deno" / "bin" / "deno"
    if fallback.exists():
        return str(fallback)
    raise RuntimeError("Deno not found. Install it: curl -fsSL https://deno.land/install.sh | sh")


@dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int
    truncated: bool = False
    timed_out: bool = False
    tool_calls: list[dict[str, object]] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


def build_deno_command(script_path: str, context_json: str) -> list[str]:
    """Build the Deno command with strict permission flags.

    Permissions granted:
    - --allow-read: only the bootstrap script directory (for imports)
    - --allow-env: RUNOWL_CONTEXT (injected context), PATH
    - No network, no write, no subprocess, no FFI, no hrtime

    The agent Python code is executed by the bootstrap which enforces
    the tool whitelist. Any attempt to import disallowed modules or call
    disallowed tools raises an error inside the sandbox.
    """
    deno = _deno_bin()
    bootstrap_dir = str(Path(script_path).parent)

    return [
        deno,
        "run",
        f"--allow-read={bootstrap_dir}",
        "--allow-env=RUNOWL_CONTEXT,RUNOWL_AGENT_CODE,PATH",
        "--no-prompt",
        "--quiet",
        script_path,
    ]


def validate_tool_call(tool_name: str) -> None:
    """Raise ValueError if the tool is not in the whitelist."""
    if tool_name not in ALLOWED_TOOLS:
        raise ValueError(
            f"Tool {tool_name!r} is not allowed in the sandbox. "
            f"Allowed tools: {sorted(ALLOWED_TOOLS)}"
        )


async def run_in_sandbox(
    code: str,
    context: dict[str, object],
    timeout: int = EXECUTION_TIMEOUT,
) -> ExecutionResult:
    """Execute agent code inside the Deno sandbox.

    Args:
        code:     Python-like agent script to execute.
        context:  Serializable dict injected as RUNOWL_CONTEXT env var.
        timeout:  Wall-clock timeout in seconds.

    Returns:
        ExecutionResult with captured output and metadata.
    """
    # Validate that the code only references allowed tools before execution
    for tool in _extract_tool_calls(code):
        validate_tool_call(tool)

    context_json = json.dumps(context)

    cmd = build_deno_command(str(_BOOTSTRAP), context_json)
    env = {
        **os.environ,
        "RUNOWL_CONTEXT": context_json,
        "RUNOWL_AGENT_CODE": code,
    }

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        try:
            raw_out, raw_err = await asyncio.wait_for(
                proc.communicate(input=code.encode()),
                timeout=timeout,
            )
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            logger.warning("Sandbox execution timed out after %ds", timeout)
            return ExecutionResult(
                stdout="",
                stderr=f"Execution timed out after {timeout}s",
                exit_code=-1,
                timed_out=True,
            )

        truncated = False
        stdout = raw_out.decode("utf-8", errors="replace")
        stderr = raw_err.decode("utf-8", errors="replace")

        if len(raw_out) + len(raw_err) > MAX_OUTPUT_BYTES:
            truncated = True
            stdout = stdout[: MAX_OUTPUT_BYTES // 2]
            stderr = stderr[: MAX_OUTPUT_BYTES // 2]

        tool_calls = _parse_tool_calls(stdout)

        return ExecutionResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode or 0,
            truncated=truncated,
            tool_calls=tool_calls,
        )

    except Exception as exc:
        logger.exception("Sandbox execution failed: %s", exc)
        return ExecutionResult(
            stdout="",
            stderr=str(exc),
            exit_code=1,
        )


def _extract_tool_calls(code: str) -> list[str]:
    """Extract tool names referenced in agent code for pre-flight validation."""
    found = []
    for tool in ALLOWED_TOOLS | {"READ_FILE", "WRITE_FILE", "EXEC", "SHELL"}:
        if tool in code:
            found.append(tool)
    return found


def _parse_tool_calls(stdout: str) -> list[dict[str, object]]:
    """Parse structured tool call results from sandbox stdout.

    The bootstrap emits lines prefixed with TOOL_CALL: followed by JSON.
    """
    calls = []
    for line in stdout.splitlines():
        if line.startswith("TOOL_CALL:"):
            try:
                calls.append(json.loads(line[len("TOOL_CALL:") :]))
            except json.JSONDecodeError:
                logger.debug("Failed to parse tool call line: %s", line)
    return calls
