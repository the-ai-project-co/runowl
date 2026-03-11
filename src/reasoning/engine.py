"""Recursive Reasoning Engine (RLM) — reason → tool call → refine loop."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from pathlib import Path

from google import genai
from google.genai import types

from github.client import GitHubClient
from github.models import PRMetadata, PRRef
from reasoning.models import (
    ConversationMessage,
    ReasoningStep,
    ReasoningTrace,
    RLMResult,
    StepType,
)
from reasoning.prompts import QA_USER_PROMPT, REVIEW_USER_PROMPT, SYSTEM_PROMPT
from sandbox.limits import MAX_ITERATIONS, MAX_LLM_CALLS

logger = logging.getLogger(__name__)

# Gemini model to use for review and Q&A
REVIEW_MODEL = "gemini-2.0-flash"

# Tool declarations for Gemini function calling
_TOOLS = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="FETCH_FILE",
            description="Fetch the full content of a file from the repository at the PR head commit.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(
                        type=types.Type.STRING,
                        description="Repository-relative file path, e.g. src/auth.py",
                    )
                },
                required=["path"],
            ),
        ),
        types.FunctionDeclaration(
            name="LIST_DIR",
            description="List the contents of a directory in the repository.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(
                        type=types.Type.STRING,
                        description="Repository-relative directory path, e.g. src/",
                    )
                },
                required=["path"],
            ),
        ),
        types.FunctionDeclaration(
            name="SEARCH_CODE",
            description="Search for code patterns across the repository.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query": types.Schema(
                        type=types.Type.STRING,
                        description="Search query, e.g. 'def authenticate' or 'JWT_SECRET'",
                    )
                },
                required=["query"],
            ),
        ),
    ]
)

# Step callback type: receives a ReasoningStep as the engine progresses
StepCallback = Callable[[ReasoningStep], None]


class ReasoningEngine:
    """Recursive Reasoning Loop (RLM) over a GitHub PR.

    Flow per iteration:
    1. Send conversation history + system prompt to Gemini.
    2. If Gemini returns a tool call → execute it via GitHubClient → append result → repeat.
    3. If Gemini returns a text response → that is the final output.
    4. Stop when max iterations or max LLM calls are reached.

    Execution traces are saved to ~/.runowl/traces/<pr_ref>.json.
    """

    def __init__(
        self,
        github_client: GitHubClient,
        api_key: str | None = None,
        step_callback: StepCallback | None = None,
    ) -> None:
        self._gh = github_client
        self._step_cb = step_callback
        api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._gemini = genai.Client(api_key=api_key)

    def _emit(self, step: ReasoningStep, trace: ReasoningTrace) -> None:
        trace.add_step(step)
        if self._step_cb:
            self._step_cb(step)

    # ── Tool execution ────────────────────────────────────────────────────────

    async def _execute_tool(
        self, name: str, args: dict[str, str], ref: PRRef, head_sha: str
    ) -> str:
        """Dispatch a Gemini tool call to the GitHubClient."""
        try:
            if name == "FETCH_FILE":
                path = args.get("path", "")
                result = await self._gh.get_file(ref, path, head_sha)
                return result.content[:8000]  # cap to avoid context explosion

            if name == "LIST_DIR":
                path = args.get("path", "")
                entries = await self._gh.list_dir(ref, path, head_sha)
                lines = [f"{e.type:4}  {e.path}" for e in entries]
                return "\n".join(lines)

            if name == "SEARCH_CODE":
                query = args.get("query", "")
                results = await self._gh.search_code(ref, query)
                lines = [f"{r.path} (score={r.score:.2f})" for r in results]
                return "\n".join(lines) if lines else "No results found."

            return f"Unknown tool: {name}"

        except Exception as exc:
            logger.warning("Tool %s failed: %s", name, exc)
            return f"Error: {exc}"

    # ── Core loop ─────────────────────────────────────────────────────────────

    async def run(
        self,
        user_prompt: str,
        ref: PRRef,
        head_sha: str,
        conversation: list[ConversationMessage] | None = None,
    ) -> RLMResult:
        """Run the reasoning loop and return the final result."""
        trace = ReasoningTrace()
        history: list[ConversationMessage] = list(conversation or [])
        history.append(ConversationMessage(role="user", content=user_prompt))

        output = ""
        error: str | None = None

        for iteration in range(MAX_ITERATIONS):
            if trace.llm_calls >= MAX_LLM_CALLS:
                logger.warning("Max LLM calls (%d) reached", MAX_LLM_CALLS)
                break

            trace.iterations = iteration + 1

            self._emit(
                ReasoningStep(
                    type=StepType.REASONING,
                    content=f"Iteration {iteration + 1}",
                    iteration=iteration,
                ),
                trace,
            )

            # Build Gemini contents from conversation history
            contents = [
                types.Content(
                    role=msg.role,
                    parts=[types.Part(text=msg.content)],
                )
                for msg in history
            ]

            try:
                response = self._gemini.models.generate_content(
                    model=REVIEW_MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        tools=[_TOOLS],
                        temperature=0.2,
                    ),
                )
            except Exception as exc:
                error = str(exc)
                logger.error("Gemini call failed: %s", exc)
                break

            self._emit(
                ReasoningStep(
                    type=StepType.LLM_CALL, content="Gemini response received", iteration=iteration
                ),
                trace,
            )

            candidate = response.candidates[0] if response.candidates else None
            if not candidate:
                error = "No candidates returned from Gemini"
                break

            # Check for tool calls
            content_parts = candidate.content.parts if candidate.content else []
            tool_calls = [
                part.function_call
                for part in (content_parts or [])
                if part.function_call is not None
            ]

            if tool_calls:
                # Append model's tool-call turn to history
                history.append(
                    ConversationMessage(
                        role="model",
                        content=json.dumps(
                            [{"name": tc.name, "args": dict(tc.args or {})} for tc in tool_calls]
                        ),
                    )
                )

                # Execute each tool and collect results
                tool_results: list[str] = []
                for tc in tool_calls:
                    self._emit(
                        ReasoningStep(
                            type=StepType.TOOL_CALL,
                            content=f"{tc.name}({tc.args})",
                            iteration=iteration,
                            metadata={"tool": tc.name, "args": dict(tc.args or {})},
                        ),
                        trace,
                    )
                    result = await self._execute_tool(
                        tc.name or "", dict(tc.args or {}), ref, head_sha
                    )
                    tool_results.append(f"## {tc.name} result\n{result}")

                # Append tool results as user turn
                history.append(
                    ConversationMessage(
                        role="user",
                        content="\n\n".join(tool_results),
                    )
                )
                continue  # next iteration

            # No tool calls → extract final text output
            final_parts = candidate.content.parts if candidate.content else []
            text_parts = [part.text for part in (final_parts or []) if part.text]
            output = "\n".join(text_parts)
            history.append(ConversationMessage(role="model", content=output))

            self._emit(
                ReasoningStep(type=StepType.OUTPUT, content=output, iteration=iteration),
                trace,
            )
            break

        self._save_trace(trace, ref)

        return RLMResult(
            output=output,
            trace=trace,
            conversation=history,
            success=bool(output) and error is None,
            error=error,
        )

    # ── Review entry point ────────────────────────────────────────────────────

    async def review_pr(
        self,
        metadata: PRMetadata,
        diff_context: str,
        ref: PRRef,
    ) -> RLMResult:
        """Run a full PR review through the reasoning loop."""
        prompt = REVIEW_USER_PROMPT.format(
            title=metadata.title,
            author=metadata.author,
            head_branch=metadata.head_branch,
            base_branch=metadata.base_branch,
            changed_files=metadata.changed_files,
            additions=metadata.additions,
            deletions=metadata.deletions,
            body=metadata.body or "(none)",
            diff_context=diff_context,
        )
        return await self.run(prompt, ref, metadata.head_sha)

    # ── Q&A entry point ───────────────────────────────────────────────────────

    async def ask(
        self,
        question: str,
        pr_context: str,
        selected_code: str,
        ref: PRRef,
        head_sha: str,
        conversation: list[ConversationMessage] | None = None,
    ) -> RLMResult:
        """Answer a question about a PR, maintaining conversation history."""
        prompt = QA_USER_PROMPT.format(
            pr_context=pr_context,
            selected_code=selected_code or "(none)",
            question=question,
        )
        return await self.run(prompt, ref, head_sha, conversation)

    # ── Trace persistence ─────────────────────────────────────────────────────

    def _save_trace(self, trace: ReasoningTrace, ref: PRRef) -> None:
        """Persist execution trace to ~/.runowl/traces/."""
        try:
            traces_dir = Path.home() / ".runowl" / "traces"
            traces_dir.mkdir(parents=True, exist_ok=True)
            trace_file = traces_dir / f"{ref.owner}__{ref.repo}__pr{ref.number}.json"
            data = {
                "iterations": trace.iterations,
                "llm_calls": trace.llm_calls,
                "tool_calls": trace.tool_calls,
                "steps": [
                    {
                        "type": step.type,
                        "iteration": step.iteration,
                        "content": step.content[:500],
                        "metadata": step.metadata,
                    }
                    for step in trace.steps
                ],
            }
            trace_file.write_text(json.dumps(data, indent=2))
        except Exception as exc:
            logger.warning("Failed to save trace: %s", exc)
