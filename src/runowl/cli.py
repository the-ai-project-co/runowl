"""RunOwl command-line interface."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from config import Settings
from github.client import GitHubClient
from github.models import PRRef
from qa.engine import QAEngine
from reasoning.engine import ReasoningEngine
from review.agent import ReviewAgent
from review.formatter import format_review_json, format_review_markdown
from review.models import ReviewResult

app = typer.Typer(
    name="runowl",
    help="AI-powered code review and Q&A for GitHub pull requests.",
    add_completion=False,
)

console = Console()

_PR_URL_RE = re.compile(
    r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)"
)


def _parse_pr_url(url: str) -> PRRef:
    m = _PR_URL_RE.match(url)
    if not m:
        console.print(f"[red]Invalid GitHub PR URL:[/red] {url}")
        raise typer.Exit(code=1)
    return PRRef(
        owner=m.group("owner"),
        repo=m.group("repo"),
        number=int(m.group("number")),
    )


def _settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def _print_rich_review(result: ReviewResult, *, quiet: bool) -> None:
    if not result.findings:
        console.print(Panel("[green]✓ No issues found[/green]", title="RunOwl Review"))
        return
    md = format_review_markdown(result)
    if not quiet:
        console.print(Markdown(md))
    else:
        console.print(md)


@app.command()
def review(
    url: str = typer.Option(..., "--url", "-u", help="GitHub PR URL"),
    expert: bool = typer.Option(False, "--expert", help="Enable expert reasoning mode"),
    output: str = typer.Option(
        "rich", "--output", "-o", help="Output format: rich | json | markdown"
    ),
    submit: bool = typer.Option(False, "--submit", help="Post review as a GitHub PR comment"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress decorative output"),
    test: bool = typer.Option(False, "--test", help="Generate and run tests after review"),
    test_only: bool = typer.Option(
        False, "--test-only", help="Generate and run tests without code review"
    ),
) -> None:
    """Review a GitHub pull request with AI."""
    if output not in ("rich", "json", "markdown"):
        console.print(f"[red]Invalid output format:[/red] {output!r}. Choose: rich, json, markdown")
        raise typer.Exit(code=1)

    try:
        settings = _settings()
    except Exception as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(code=1)

    ref = _parse_pr_url(url)

    from testing.executor import execute_suite
    from testing.generator import TestGenerationAgent
    from testing.models import TestSuite
    from testing.results import format_results_json, format_results_markdown

    async def _run() -> tuple[Optional[ReviewResult], Optional[TestSuite]]:
        client = GitHubClient(token=settings.github_token)
        try:
            review_result: Optional[ReviewResult] = None
            suite: Optional[TestSuite] = None

            if not test_only:
                reasoning = ReasoningEngine(
                    github_client=client,
                    api_key=settings.gemini_api_key,
                )
                agent = ReviewAgent(
                    github_client=client,
                    reasoning_engine=reasoning,
                )
                review_result = await agent.review(ref)

            if test or test_only:
                if not settings.anthropic_api_key:
                    console.print(
                        "[yellow]Warning:[/yellow] ANTHROPIC_API_KEY not set — "
                        "skipping test generation"
                    )
                else:
                    metadata = await client.get_pr_metadata(ref)
                    test_agent = TestGenerationAgent(client, settings.anthropic_api_key)
                    gen = await test_agent.generate(ref, metadata)
                    if gen.success:
                        suite = await execute_suite(gen.suite, metadata.body or "")
                    else:
                        suite = gen.suite

            return review_result, suite
        finally:
            await client.close()

    review_result, suite = asyncio.run(_run())

    # --- Output review results ---
    if review_result is not None:
        if output == "json":
            data = format_review_json(review_result)
            if suite is not None:
                data["tests"] = format_results_json(suite)
            console.print(json.dumps(data, indent=2) if not quiet else json.dumps(data))
        elif output == "markdown":
            console.print(format_review_markdown(review_result))
            if suite is not None:
                console.print(format_results_markdown(suite))
        else:
            _print_rich_review(review_result, quiet=quiet)
            if suite is not None:
                console.print(Markdown(format_results_markdown(suite)))
    elif test_only and suite is not None:
        # --test-only: no review output, only test results
        if output == "json":
            console.print(
                json.dumps(format_results_json(suite), indent=2) if not quiet
                else json.dumps(format_results_json(suite))
            )
        else:
            console.print(Markdown(format_results_markdown(suite)))

    # Exit with code 1 if review found blocking issues
    if review_result is not None and review_result.findings:
        raise typer.Exit(code=1)


@app.command()
def ask(
    url: str = typer.Option(..., "--url", "-u", help="GitHub PR URL"),
    question: str = typer.Option(..., "--question", "-q", help="Question to ask about the PR"),
) -> None:
    """Ask a question about a GitHub pull request."""
    try:
        settings = _settings()
    except Exception as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(code=1)

    ref = _parse_pr_url(url)

    async def _run() -> str:
        client = GitHubClient(token=settings.github_token)
        try:
            reasoning = ReasoningEngine(
                github_client=client,
                api_key=settings.gemini_api_key,
            )
            engine = QAEngine(
                github_client=client,
                reasoning_engine=reasoning,
            )
            msg = await engine.ask(ref, question)
            return msg.answer
        finally:
            await client.close()

    answer = asyncio.run(_run())
    console.print(answer)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
