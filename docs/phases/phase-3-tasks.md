# RunOwl — Phase 3 Tasks: Intelligence & Ecosystem

## 1. Skill / Agent Integration

- [ ] Write SKILL.md definition file for RunOwl
- [ ] Define skill capabilities (review, test, ask)
- [ ] Define required environment variables (GEMINI_API_KEY, GITHUB_TOKEN)
- [ ] Package as installable skill (`npx skills add runowl`)
- [ ] Test integration with Claude Code
- [ ] Test integration with Cursor
- [ ] Test integration with Codex
- [ ] Test integration with other agentic platforms
- [ ] Write skill usage documentation
- [ ] Write tests for skill interface

## 2. CI/CD Output

- [ ] Design structured JSON output schema for reviews
  - [ ] PR metadata
  - [ ] Findings array (severity, type, description, citations)
  - [ ] Test results array (name, status, duration, error)
  - [ ] Summary statistics
- [ ] Design structured JSON output schema for test results
- [ ] Build Markdown report generator
  - [ ] Summary section (pass/fail counts, severity breakdown)
  - [ ] Findings table with severity badges
  - [ ] Test results table with status indicators
  - [ ] Links to video/replay for failures
- [ ] Build GitHub Actions action (`runowl/review-action`)
  - [ ] Action YAML definition
  - [ ] Input parameters (url, question, expert, tier)
  - [ ] Output parameters (status, findings_count, test_results)
  - [ ] Post results as PR comment
  - [ ] Set check run status (pass/fail)
- [ ] Implement exit codes for CI gates
  - [ ] Exit 0: no P0/P1 findings, all tests pass
  - [ ] Exit 1: P0 or P1 findings found, or tests failed
  - [ ] Configurable severity threshold for failure
- [ ] Publish action to GitHub Marketplace
- [ ] Write tests for all output formats

## 3. Real-Time Reporting

- [ ] Build reporting dashboard page in web UI
- [ ] Implement per-PR report view
  - [ ] Review findings with severity breakdown
  - [ ] Test results with pass/fail/skip counts
  - [ ] Timeline of review + test execution
- [ ] Implement screenshot capture during test execution
  - [ ] Capture on test failure
  - [ ] Capture at key assertions
  - [ ] Store and display in report
- [ ] Build log aggregation system
  - [ ] Collect agent reasoning logs
  - [ ] Collect test execution stdout/stderr
  - [ ] Collect sandbox execution logs
  - [ ] Display logs in expandable sections in report
- [ ] Build exportable reports
  - [ ] PDF export
  - [ ] HTML export (self-contained, shareable)
- [ ] Write tests for reporting features

## 4. AI-Generated Follow-Up Suggestions

- [ ] Build suggestion engine
- [ ] Input: PR context (title + body, truncated), conversation history (last 3 messages), last AI answer (truncated)
- [ ] Output: 4–5 short follow-up questions (max 5 words each)
- [ ] Use lightweight sub-model for speed (not main review model)
- [ ] Build suggestion display in chat panel (clickable chips)
- [ ] Refresh suggestions after each Q&A exchange
- [ ] Build API endpoint: `POST /api/suggestions`
- [ ] Write tests for suggestion quality and format

## 5. Regression Detection

- [ ] Design data model for tracking findings across PRs
  - [ ] Finding fingerprint (hash of type + location + pattern)
  - [ ] PR association
  - [ ] Timestamp
  - [ ] Resolution status (open, fixed, ignored)
- [ ] Build finding persistence layer (database)
- [ ] Implement finding deduplication across PRs
- [ ] Detect recurring patterns:
  - [ ] Same finding type appearing in multiple PRs
  - [ ] Same code path flagged repeatedly
  - [ ] Same author introducing similar issues
- [ ] Build regression trend tracking
  - [ ] Weekly/monthly finding counts by severity
  - [ ] Finding resolution rate
  - [ ] Average time to fix
- [ ] Build regression dashboard in web UI
  - [ ] Trend charts (findings over time)
  - [ ] Top recurring issues
  - [ ] Hotspot files (most frequently flagged)
- [ ] Implement regression alerts
  - [ ] Alert when finding count spikes above baseline
  - [ ] Alert when a previously fixed issue reappears
- [ ] Write tests for regression detection logic
