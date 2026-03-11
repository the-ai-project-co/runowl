# RunOwl — Milestones (Free Tier)

> Paid-tier milestones (Deep Security, SOLID, Team Management, Regression Detection, Integrations & Scale, Enterprise) are tracked in `runowl-paid/docs/milestones.md`.

---

## Phase 1 — MVP: AI Code Review ✅

### Milestone 1.1: Core Review Engine
- [x] Set up Python/FastAPI project structure
- [x] Implement recursive reasoning loop (RLM) with Gemini
- [x] Build GitHub API integration (fetch PR diffs, files, metadata)
- [x] Implement code review agent with repo exploration tools (fetch_file, list_dir, search_code)
- [x] Build Deno sandbox for safe code execution during review
- [x] Implement citation system (file path + line number references)

### Milestone 1.2: Severity & Classification
- [x] Implement finding severity levels (P0 — critical, P1 — high, P2 — medium, P3 — low)
- [x] Implement finding categories (bug, security, investigation, informational)
- [x] Build structured output format for findings

### Milestone 1.3: Interactive Q&A
- [x] Build Q&A engine on PR diffs
- [x] Implement conversation history and context management
- [x] Support code selection (range, hunk, file, changeset)

### Milestone 1.4: Surface-Level Security (Free)
- [x] Basic input validation checks
- [x] Hardcoded secrets detection
- [x] Obvious injection pattern detection
- [x] Missing auth checks on endpoints

### Milestone 1.5: CLI Tool
- [x] Build `npx runowl` CLI package
- [x] Implement `review` command with --url and --question flags
- [x] Implement --expert flag (activates paid deep analysis)
- [x] Support text, markdown, and JSON output formats
- [x] Implement --submit flag to post results as PR comments
- [x] Implement --quiet flag for CI/CD usage

### Milestone 1.6: GitHub Integration
- [x] PR event webhook listener
- [x] Auto-trigger review on PR open
- [x] Post findings as PR comments with severity badges
- [x] Support both public and private repositories

### Milestone 1.7: Freemium Gate
- [x] Implement license/tier detection
- [x] Gate deep security and SOLID features behind paid tier
- [x] Build upgrade prompts for free users hitting paid features

---

## Phase 2a — Testing Engine

### Milestone 2a.1: Test Generation
- [ ] Build test generation agent from code diffs
- [ ] Generate test cases from natural language descriptions
- [ ] Support multiple test frameworks (Jest, Pytest, Playwright)
- [ ] Map generated tests to changed code paths

### Milestone 2a.2: Sandboxed Execution
- [ ] Build Deno-based sandbox for unit/integration tests
- [ ] Implement test runner with result collection
- [ ] Build Docker container setup for browser testing
- [ ] Implement parallel test execution

### Milestone 2a.3: Real Browser Testing
- [ ] Set up browser automation infrastructure (Playwright in Docker)
- [ ] Implement real browser test execution
- [ ] Support multiple browsers (Chrome, Firefox)
- [ ] Build preview app URL detection and connection

### Milestone 2a.4: Video & Replay
- [ ] Implement video recording of test execution
- [ ] Build session replay from recorded events
- [ ] Link video timestamps to specific test assertions
- [ ] Store and serve recordings

---

## Phase 2b — Platform & Management (Free Portions)

### Milestone 2b.1: Web UI
- [ ] Set up Next.js project
- [ ] Build diff viewer with syntax highlighting
- [ ] Build chat panel (code review tab, flags tab, bugs tab)
- [ ] Implement PR loading and file browser
- [ ] Build real-time streaming of review results
- [ ] Implement citation click-to-navigate

> Team Management, Test Suite Management, and Billing are tracked in `runowl-paid/docs/phases/phase-2b-paid-tasks.md`.

---

## Phase 3 — Intelligence & Ecosystem (Free Portions)

### Milestone 3.1: Agent/Skill Integration
- [ ] Build SKILL.md definition for RunOwl
- [ ] Package as installable skill (`npx skills add runowl`)
- [ ] Test integration with Claude, Cursor, Codex
- [ ] Document skill usage and capabilities

### Milestone 3.2: CI/CD Output
- [ ] Structured JSON output schema
- [ ] Markdown report generation
- [ ] GitHub Actions marketplace action
- [ ] Exit codes for CI pass/fail gates

### Milestone 3.3: Reporting
- [ ] Real-time reporting dashboard
- [ ] Screenshot capture during test execution
- [ ] Log aggregation and display
- [ ] Exportable reports (PDF, HTML)

### Milestone 3.4: Follow-up Suggestions
- [ ] Build suggestion engine from conversation context
- [ ] Generate 4–5 contextual next questions per review
- [ ] Use lightweight sub-model for speed

> Regression Detection is tracked in `runowl-paid/docs/phases/phase-3-paid-tasks.md`.
> Integrations & Scale (Phase 4) and Enterprise (Phase 5) are tracked entirely in `runowl-paid/docs/`.
