# Changelog

All notable changes to RunOwl are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
RunOwl uses [semantic versioning](https://semver.org/).

---

## [Unreleased]

---

## [0.2.0] — 2026-03-11

### Changed

**Monorepo workspace restructure**
- Split into three independent repositories inside the `RunOwl/` workspace:
  - `runowl/` — public open-source core (this repo, MIT license)
  - `runowl-paid/` — private paid extensions (Team / Business / Enterprise, proprietary)
  - `runowl-website/` — SvelteKit marketing site and docs
- Paid modules (`src/security/deep_checks.py`, `src/architecture/solid.py`, `src/architecture/checks.py`) replaced with `NotImplementedError` stubs in this repo; full implementations live in `runowl-paid`
- `.gitignore` updated to match new repo boundaries

**Docs restructure (Option B segregation)**
- `docs/phases/` — free-only task lists retained here (Phases 1–3 free portions)
- Paid phase content moved to `runowl-paid/docs/phases/`:
  - Phase 1: Deep Security + SOLID tasks → `phase-1-paid-tasks.md`
  - Phase 2b: Team Management, Test Suite Management, Billing → `phase-2b-paid-tasks.md`
  - Phase 3: Regression Detection → `phase-3-paid-tasks.md`
  - Phase 4 (Integrations & Scale) moved entirely to `runowl-paid`
- `docs/milestones.md` — stripped to free-tier phases only; full version in `runowl-paid`
- Brand strategy, product roadmap, and Phase 5 tasks moved to `runowl-paid/docs/`
- `docs/launch/` — launch content (blog post, Product Hunt listing, launch posts)

---

## [0.1.0] — 2026-03-11

Initial release of RunOwl — AI-powered PR code review agent.

### Added

**Core infrastructure**
- Python 3.12+ project with `src/` layout, `pyproject.toml`, uv package manager
- FastAPI application with `/health` endpoint and CORS middleware
- Pydantic-settings configuration with `Settings`, `Tier`, and `Env` enums
- `.env.example` with all configuration options documented

**GitHub API Layer** (`src/github/`)
- `GitHubClient` — async httpx client with GITHUB_TOKEN auth, exponential backoff, LRU cache (200 entries), concurrency limit (5 concurrent requests)
- `parse_pr_url()` — extracts owner/repo/number from GitHub PR URLs
- `sanitize_path()` — blocks path traversal attacks in file fetching
- `parse_patch()` — parses unified diffs into structured `DiffHunk` objects
- Methods: `get_pr_metadata`, `get_file`, `list_dir`, `search_code`, `post_pr_comment`, `create_check_run`, `update_check_run`

**Deno Sandbox** (`src/sandbox/`)
- Isolated code execution via Deno 2.x with strict permission flags
- Tool whitelist: `FETCH_FILE`, `LIST_DIR`, `SEARCH_CODE` only
- Iteration limits: max 20 iterations, 15 LLM calls, 60s timeout, 256KB output cap
- Pre-flight tool validation before execution
- `bootstrap.ts` — Deno entry point with tool enforcement

**Recursive Reasoning Engine** (`src/reasoning/`)
- `ReasoningEngine` — full Gemini function-calling RLM loop
- `build_diff_context()` — up to 50 files inline, overflow noted with FETCH_FILE hints
- Conversation history management across turns
- Execution traces saved to `~/.runowl/traces/`
- System prompt, review prompt, Q&A prompt

**Code Review Agent** (`src/review/`)
- `ReviewAgent` — orchestrates fetch → diff → RLM → parse → reclassify → validate
- `parse_findings()` — extracts structured findings from agent output
- `Citation` validation — constrains findings to visible diff hunks only
- `Severity` system: P0 (critical) → P3 (low)
- `FindingType`: bug, security, investigation, informational
- `reclassify_findings()` — keyword-based promotion prevents under-classification
- `ensure_fix_for_blocking()` — guarantees P0/P1 findings have fix suggestions
- `format_review_markdown()` — GitHub PR comment body
- `format_review_json()` — structured CI/CD output

**Interactive Q&A** (`src/qa/`)
- `QAEngine` — session-aware question answering over PR diffs
- Code selection modes: line, range, hunk, file, changeset
- Conversation history (last 6 exchanges as context)
- Commands: `quit`, `reset`, `history`, `files`, `info`

**Surface Security Analysis** (`src/security/`) — free tier
- `check_hardcoded_secrets()` — passwords, API keys, tokens in source code
- `check_sql_injection()` — f-string/concat/format string queries
- `check_xss()` — innerHTML, document.write, dangerouslySetInnerHTML, render_template_string
- `check_missing_auth()` — new routes without auth decorators
- `check_exposed_env()` — secrets logged or returned in responses
- `check_unpinned_dependencies()` — bare package names, `>=`, `^` versions
- Scans only `+` lines (new code introduced by the PR)
- `run_surface_scan()` — orchestrator with binary/lock file skipping and deduplication

**Deep Security Analysis** (`src/security/deep_checks.py`) — paid tier
- OWASP A01: Broken access control (IDOR, missing ownership filters)
- OWASP A02: Cryptographic failures (MD5/SHA1, DES/ECB, hardcoded IV, weak random)
- OWASP A03: Injection — command injection, NoSQL injection, template injection
- OWASP A05: Security misconfiguration (CORS wildcard, debug mode)
- OWASP A07: Auth failures — JWT none-alg, weak secrets, missing exp, session fixation
- Race conditions — TOCTOU, unsynchronized shared state
- Supply chain — typosquatting detection, eval of network content
- `run_deep_scan()` — orchestrator, all hits marked `is_free=False`

**SOLID / Architecture Analysis** (`src/architecture/`) — paid tier
- S: Single responsibility — mixed HTTP+DB concerns, god objects (10+ public methods)
- O: Open/closed — long if/elif chains (5+) dispatching on type/value
- L: Liskov substitution — multi-type isinstance checks, no-op overrides
- I: Interface segregation — fat ABCs (7+ abstract methods), stub implementations
- D: Dependency inversion — concrete class instantiation inside `__init__`
- Code smells: long methods (40+ lines), deep nesting (4+ levels), feature envy (4+ chained calls)
- `run_solid_scan()` — orchestrator, skips non-code files

**CLI Tool** (`cli/`) — `npx runowl`
- TypeScript npm package with Node.js ESM
- `runowl review` — full review with all flags (`--expert`, `--output`, `--submit`, `--quiet`, `--model`)
- `runowl ask` — single question or interactive REPL
- Auto-discovers Python: `uv run` → `python3` → `python`
- Streams stdout/stderr from Python backend
- Python CLI (`src/runowl/cli.py`) — Typer app with Rich progress, table output, interactive Q&A REPL

**GitHub PR Integration** (`src/webhook/`)
- `POST /webhook/github` — receives PR events (opened, synchronize, reopened)
- HMAC-SHA256 signature verification via `X-Hub-Signature-256`
- Background async review job: Check Run → ReviewAgent → PR comment → Check Run update
- GitHub Check Runs API — `in_progress` → `success`/`failure` based on blocking findings
- Non-review events and actions ignored gracefully

**Freemium Gate** (`src/freemium/`)
- `Feature` enum — 12 features across 4 tiers
- `check_feature()` / `require_feature()` — tier-based access control
- `FeatureGatedError` — structured error with upgrade URL and message
- `detect_tier()` — env var priority → API key → free default
- `format_upgrade_prompt_cli()` / `format_upgrade_prompt_markdown()` — upgrade prompts
- `GET /license/tier`, `POST /license/validate`, `GET /license/features` endpoints

**Test suite** — 390 tests, all passing
- Covers all modules: GitHub, sandbox, reasoning, review, Q&A, security, architecture, CLI, webhook, freemium
- No real API calls in tests — all external services mocked

[0.1.0]: https://github.com/the-ai-project-co/RunOwl/releases/tag/v0.1.0
