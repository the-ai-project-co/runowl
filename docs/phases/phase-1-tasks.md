# RunOwl — Phase 1 Tasks: AI Code Review (MVP)

## 1. Project Setup

- [x] Initialize Python project with `pyproject.toml`
- [x] Set up FastAPI application skeleton
- [x] Configure `uv` as package manager
- [x] Set up linting (ruff) and formatting (black)
- [x] Create `.env.example` with required environment variables
- [x] Set up GitHub repository with MIT license
- [x] Create CI pipeline (GitHub Actions) for linting and tests
- [x] Write initial README with project description and quick start

## 2. GitHub API Layer

- [x] Build GitHub URL parser (extract owner, repo, PR number from URL)
- [x] Implement PR metadata fetcher (title, body, author, commits, file list, change stats)
- [x] Implement PR diff fetcher (per-file diffs with hunks)
- [x] Implement file content fetcher (base and head versions)
- [x] Implement code search via GitHub API
- [x] Implement directory listing via GitHub API
- [x] Add authentication handling (GITHUB_TOKEN for private repos, unauthenticated for public)
- [x] Add rate limit handling with exponential backoff
- [x] Add file caching (200-entry limit) to reduce API calls
- [x] Add concurrency control (max 5 simultaneous GitHub requests)
- [x] Add path sanitization to prevent traversal attacks
- [x] Write tests for all GitHub API functions

## 3. Deno Sandbox

- [x] Set up Deno 2.x as execution sandbox
- [x] Build `build_deno_command()` for isolated Python execution
- [x] Implement tool whitelist (SEARCH_CODE, FETCH_FILE, LIST_DIR only)
- [x] Block all other file operations (open(), os.path, etc.)
- [x] Implement iteration limits (MAX_ITERATIONS, MAX_LLM_CALLS)
- [x] Implement data isolation (only serializable data injected)
- [x] Cache Deno dependencies for fast startup
- [x] Write tests for sandbox security boundaries

## 4. Recursive Reasoning Engine (RLM)

- [x] Set up Gemini API integration
- [x] Build recursive reasoning loop: reason → generate code → execute → refine
- [x] Implement step callbacks for progress reporting
- [x] Implement agent tool access (fetch_file, list_dir, search_code)
- [x] Build diff context builder (up to 100 files, 50 in prompt, rest via REPL)
- [x] Implement conversation history management
- [x] Save execution traces to `~/.runowl/traces/`
- [x] Write tests for reasoning loop

## 5. Code Review Agent

- [x] Build review prompt system
- [x] Implement finding extraction from agent output
- [x] Build citation generation (file path + line range references)
- [x] Constrain citations to visible diff hunks
- [x] Implement output parsing into structured blocks (markdown + code snippets)
- [x] Write tests for review quality

## 6. Severity & Classification System

- [x] Define severity levels: P0 (critical), P1 (high), P2 (medium), P3 (low)
- [x] Define finding types: bug, security, investigation, informational
- [x] Build severity assignment logic
- [x] Build structured finding output format
- [x] Include fix suggestions for P0 and P1 findings
- [x] Write tests for classification accuracy

## 7. Interactive Q&A

- [x] Build Q&A engine that accepts questions about PR diffs
- [x] Implement code selection modes (range, single-line, hunk, file, changeset)
- [x] Maintain conversation history across multiple questions
- [x] Support context from selected code regions
- [x] Build answer formatting (markdown explanations + code snippets)
- [x] Build citation system for Q&A answers
- [x] Write tests for Q&A flow

## 8. Surface-Level Security Analysis (Free)

- [x] Hardcoded secrets detection (API keys, passwords, tokens in code)
- [x] Obvious SQL/NoSQL injection patterns
- [x] Basic XSS pattern detection
- [x] Missing authentication checks on new endpoints
- [x] Exposed environment variables or config
- [x] Unpinned dependency versions
- [x] Write tests for each detection

## 9. Deep Security Analysis (Paid)

- [x] Full OWASP Top 10 checklist implementation
  - [x] Injection (SQL, NoSQL, command, GraphQL)
  - [x] Broken authentication
  - [x] Sensitive data exposure
  - [x] XXE
  - [x] Broken access control
  - [x] Security misconfiguration
  - [x] XSS (stored, reflected, DOM)
  - [x] Insecure deserialization
  - [x] Using components with known vulnerabilities
  - [x] Insufficient logging
- [x] JWT & token security (algorithm confusion, weak secrets, missing expiry)
- [x] Cryptography checks (weak algorithms, hardcoded IVs/salts)
- [x] Race condition detection (unsynchronized shared state, TOCTOU)
- [x] Supply chain analysis (dependency confusion, untrusted imports)
- [x] CORS & security header checks (CSP, X-Frame-Options)
- [x] Runtime risk detection (unbounded loops, missing timeouts, resource exhaustion)
- [x] Data integrity checks (missing transactions, non-idempotent operations)
- [x] Write tests for each category

## 10. SOLID / Architecture Analysis (Paid)

- [x] Single Responsibility Principle detection (god objects, mixed concerns)
- [x] Open/Closed Principle detection (excessive switch/if blocks, no extension points)
- [x] Liskov Substitution detection (subclass type checks, no-op overrides)
- [x] Interface Segregation detection (fat interfaces, stub implementations)
- [x] Dependency Inversion detection (hardcoded implementations, no abstractions)
- [x] Code smell detection (long methods, deep nesting, feature envy)
- [x] Write tests for architecture analysis

## 11. CLI Tool (`npx runowl`)

- [x] Set up npm package structure
- [x] Build TypeScript CLI entry point
- [x] Build Python runner (launches Python backend from npm package)
- [x] Implement `review` command
  - [x] `--url, -u` flag (required — GitHub PR or Issue URL)
  - [x] `--question, -q` flag (custom question)
  - [x] `--expert` flag (triggers deep security + SOLID analysis)
  - [x] `--output, -o` flag (text, markdown, json)
  - [x] `--quiet` flag (suppress progress, output results only)
  - [x] `--submit` flag (post as GitHub PR comment)
  - [x] `--model, -m` flag (model selection)
  - [x] `--version, -V` flag
- [x] Implement `ask` command (interactive Q&A mode)
  - [x] `quit/exit/q` — end session
  - [x] `help` — show commands
  - [x] `reset` — clear history
  - [x] `history` — show previous Q&A
  - [x] `files` — list codebase structure
  - [x] `info` — show repo metadata
- [x] Build progress display (reasoning, code execution, output steps)
- [x] Build Rich-formatted terminal output
- [x] Build error handling and user-friendly error messages
- [x] Write tests for CLI commands
- [x] Publish to npm registry

## 12. GitHub PR Integration

- [x] Build webhook receiver for PR events (opened, synchronize, reopened)
- [x] Auto-trigger review on PR open
- [x] Format findings as GitHub PR comment (markdown with severity badges)
- [x] Support GitHub Check Runs API (pass/fail status)
- [x] Handle both public repos (Gemini key only) and private repos (+ GitHub token)
- [x] Build GitHub App configuration flow
- [x] Write tests for webhook handling

## 13. Freemium Gate

- [x] Define feature flags for free vs paid
- [x] Implement tier detection (API key / license check)
- [x] Gate deep security analysis behind paid tier
- [x] Gate SOLID/architecture analysis behind paid tier
- [x] Show upgrade prompts when free users trigger paid features
- [x] Build license validation endpoint
- [x] Write tests for gating logic

## 14. Documentation

- [x] Write README (project description, quick start, features, comparison table)
- [x] Write INSTALLATION.md (prerequisites, setup steps, environment config)
- [x] Write CONTRIBUTING.md (how to contribute, code standards, PR process)
- [x] Write CHANGELOG.md (initial release)
- [x] Add inline code comments for complex logic
- [x] Create `.env.example` with all configuration options documented

## 15. Launch Prep

- [x] Set up runowl.ai website (or similar domain)
- [x] Create GitHub organization
- [x] Publish npm package
- [x] Publish PyPI package
- [x] Write launch blog post
- [x] Prepare Product Hunt listing
- [x] Create social media accounts
- [x] Write Hacker News / Reddit launch post
