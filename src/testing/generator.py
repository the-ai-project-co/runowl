"""Test generation agent — uses Claude (Anthropic) with tool-use agentic loop.

The agent:
1. Receives the PR diff and metadata.
2. Uses FETCH_FILE / LIST_DIR / SEARCH_CODE to understand context.
3. Outputs generated test file(s) as fenced code blocks.
4. We parse those blocks into TestCase objects.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import anthropic
from anthropic.types import MessageParam, TextBlock, ToolUseBlock

from github.client import GitHubClient
from github.models import PRMetadata, PRRef
from reasoning.context import build_diff_context
from testing.detector import detect_framework, find_test_paths
from testing.models import Confidence, FrameworkType, TestCase, TestSuite, TestType
from testing.prompts import TEST_GENERATION_SYSTEM_PROMPT, TEST_GENERATION_USER_PROMPT

logger = logging.getLogger(__name__)

# Claude model for test generation
_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 8192
_MAX_ITERATIONS = 12

# Regex to extract fenced code blocks from Claude's output
_CODE_BLOCK_RE = re.compile(
    r"```(?:python|typescript|javascript|ts|js)?\n(.*?)```",
    re.DOTALL,
)
# Extract filename from first comment line in a code block
_FILENAME_RE = re.compile(r"^(?:#|//)\s*(tests?/\S+\.(?:py|ts|js|spec\.\w+))", re.MULTILINE)
# Confidence annotation: # confidence: high|medium|low
_CONFIDENCE_RE = re.compile(r"#\s*confidence:\s*(high|medium|low)", re.IGNORECASE)
# Coverage annotation: # covers: path/to/file.py:42
_COVERS_RE = re.compile(r"#\s*covers:\s*(\S+):(\d+)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Tool definitions for Claude
# ---------------------------------------------------------------------------

_TOOLS: list[dict[str, object]] = [
    {
        "name": "FETCH_FILE",
        "description": "Fetch the contents of a file in the repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Repository-relative file path"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "LIST_DIR",
        "description": "List files and directories at a path in the repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Repository-relative directory path"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "SEARCH_CODE",
        "description": "Search the codebase for a pattern or symbol.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query or symbol name"},
            },
            "required": ["query"],
        },
    },
]


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


@dataclass
class GenerationResult:
    suite: TestSuite
    raw_output: str = ""
    success: bool = False
    error: str | None = None
    tool_call_count: int = 0


class TestGenerationAgent:
    """Agentic loop that uses Claude to generate tests for a PR diff."""

    def __init__(self, github_client: GitHubClient, api_key: str) -> None:
        self._github = github_client
        self._claude = anthropic.Anthropic(api_key=api_key)

    async def generate(
        self,
        ref: PRRef,
        metadata: PRMetadata,
        step_callback: object = None,
    ) -> GenerationResult:
        """Run the test generation agent for a PR and return a TestSuite."""

        # Fetch diffs and build context
        diffs = await self._github.get_pr_files(ref)  # type: ignore[attr-defined]
        diff_context = build_diff_context(metadata, diffs)

        # Detect framework and find existing test paths
        framework = await detect_framework(self._github, ref, metadata.head_sha)
        test_paths = await find_test_paths(self._github, ref, metadata.head_sha)

        # Build initial user message
        user_content = TEST_GENERATION_USER_PROMPT.format(
            owner=ref.owner,
            repo=ref.repo,
            number=ref.number,
            title=metadata.title,
            author=metadata.author,
            head_branch=metadata.head_branch,
            base_branch=metadata.base_branch,
            changed_files=metadata.changed_files,
            additions=metadata.additions,
            deletions=metadata.deletions,
            body=metadata.body or "No description.",
            diff_context=diff_context,
            framework=framework.value,
            test_paths=", ".join(test_paths) if test_paths else "none detected",
        )

        messages: list[MessageParam] = [{"role": "user", "content": user_content}]
        raw_output = ""
        tool_call_count = 0

        suite = TestSuite(
            pr_ref=f"{ref.owner}/{ref.repo}#{ref.number}",
            framework=framework,
        )

        # ------------------------------------------------------------------
        # Agentic loop
        # ------------------------------------------------------------------
        for iteration in range(_MAX_ITERATIONS):
            try:
                response = self._claude.messages.create(
                    model=_MODEL,
                    max_tokens=_MAX_TOKENS,
                    system=TEST_GENERATION_SYSTEM_PROMPT,
                    tools=_TOOLS,  # type: ignore[arg-type]
                    messages=messages,
                )
            except Exception as exc:
                logger.error("Claude API error on iteration %d: %s", iteration, exc)
                suite.generation_error = str(exc)
                return GenerationResult(suite=suite, error=str(exc))

            # Append assistant turn to conversation
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                # Extract final text output
                for block in response.content:
                    if isinstance(block, TextBlock):
                        raw_output += block.text
                break

            if response.stop_reason == "tool_use":
                # Execute each tool call and collect results
                tool_results = []
                for block in response.content:
                    if not isinstance(block, ToolUseBlock):
                        continue
                    tool_call_count += 1
                    result_content = await self._execute_tool(
                        block.name, block.input, ref, metadata.head_sha  # type: ignore[arg-type]
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_content,
                        }
                    )

                messages.append({"role": "user", "content": tool_results})  # type: ignore[typeddict-item]
                continue

            # Any other stop reason (max_tokens etc) — capture what we have
            for block in response.content:
                if isinstance(block, TextBlock):
                    raw_output += block.text
            break

        suite.generation_raw = raw_output
        suite.cases = _parse_test_cases(raw_output, framework)
        suite.generation_success = bool(suite.cases)
        if not suite.cases:
            suite.generation_error = "No test cases parsed from agent output"

        return GenerationResult(
            suite=suite,
            raw_output=raw_output,
            success=suite.generation_success,
            tool_call_count=tool_call_count,
        )

    async def _execute_tool(
        self,
        name: str,
        args: dict[str, str],
        ref: PRRef,
        head_sha: str,
    ) -> str:
        """Execute a tool call and return the string result."""
        try:
            if name == "FETCH_FILE":
                file = await self._github.get_file(ref, args["path"], head_sha)
                # Cap at 8 KB to avoid context bloat
                content = file.content[:8192]
                return content or "(empty file)"

            if name == "LIST_DIR":
                entries = await self._github.list_dir(ref, args.get("path", ""), head_sha)
                return "\n".join(f"{e.type}  {e.name}" for e in entries) or "(empty directory)"

            if name == "SEARCH_CODE":
                results = await self._github.search_code(ref, args["query"])
                if not results:
                    return "No results found."
                lines = [
                    f"{r.path}:{getattr(r, 'line_number', '')}  {getattr(r, 'fragment', '')}"
                    for r in results[:10]
                ]
                return "\n".join(lines)

        except Exception as exc:
            logger.debug("Tool %s failed: %s", name, exc)
            return f"Error: {exc}"

        return f"Unknown tool: {name}"


# ---------------------------------------------------------------------------
# Parse Claude output → TestCase objects
# ---------------------------------------------------------------------------


def _parse_test_cases(raw_output: str, framework: FrameworkType) -> list[TestCase]:
    """Extract fenced code blocks from Claude's output and build TestCase objects."""
    cases: list[TestCase] = []
    seen_codes: set[str] = set()

    for match in _CODE_BLOCK_RE.finditer(raw_output):
        code = match.group(1).strip()
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)

        # Determine filename from first comment line
        fname_match = _FILENAME_RE.search(code)
        source_file = fname_match.group(1) if fname_match else ""

        # Confidence
        conf_match = _CONFIDENCE_RE.search(code)
        confidence = Confidence(conf_match.group(1).lower()) if conf_match else Confidence.MEDIUM

        # Coverage reference
        covers_match = _COVERS_RE.search(code)
        covers_file = covers_match.group(1) if covers_match else ""
        covers_line = int(covers_match.group(2)) if covers_match else 0

        # Detect test type from code content
        test_type = _infer_test_type(code, framework)

        # Build a name from the filename or a generic label
        name = source_file or f"generated_test_{len(cases) + 1}"

        cases.append(
            TestCase(
                name=name,
                type=test_type,
                framework=framework,
                code=code,
                source_file=covers_file,
                diff_line_start=covers_line,
                confidence=confidence,
                description=_extract_description(code),
            )
        )

    return cases


def _infer_test_type(code: str, framework: FrameworkType) -> TestType:
    lower = code.lower()
    if framework == FrameworkType.PLAYWRIGHT or "page." in lower or "browser." in lower:
        return TestType.E2E
    if "httpx" in lower or "test_client" in lower or "supertest" in lower or "/api/" in lower:
        return TestType.INTEGRATION
    return TestType.UNIT


def _extract_description(code: str) -> str:
    """Pull the first docstring or comment block as the description."""
    lines = code.splitlines()
    for line in lines[:10]:
        stripped = line.strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            return stripped.strip("\"' ")
        if (
            stripped.startswith("#")
            and not stripped.startswith("# confidence")
            and not stripped.startswith("# covers")
        ):
            return stripped.lstrip("# ").strip()
    return ""
