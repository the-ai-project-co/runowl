# RunOwl — Phase 2a Tasks: Testing Engine

## 1. Test Generation Agent

- [ ] Design test generation prompt system
- [ ] Build agent that reads PR diffs and generates test cases
- [ ] Implement natural language → test code conversion
- [ ] Support test framework detection (auto-detect Jest, Pytest, Playwright, etc.)
- [ ] Generate unit tests for changed functions
- [ ] Generate integration tests for changed API endpoints
- [ ] Generate E2E tests for changed user flows
- [ ] Map each generated test to the source code it covers
- [ ] Build confidence scoring for generated tests (high/medium/low)
- [ ] Implement test deduplication (avoid generating tests that already exist)
- [ ] Write tests for the test generator

## 2. Sandboxed Test Execution (Deno)

- [ ] Extend existing Deno sandbox for test execution
- [ ] Build test runner that executes generated unit tests
- [ ] Build test runner that executes generated integration tests
- [ ] Implement result collection (pass, fail, error, skip)
- [ ] Capture stdout/stderr from test runs
- [ ] Implement timeout handling per test
- [ ] Implement resource limits (memory, CPU)
- [ ] Build structured test result output
- [ ] Write tests for sandbox test execution

## 3. Docker Infrastructure for Browser Testing

- [ ] Design Docker container architecture for browser testing
- [ ] Create Dockerfile with Playwright + browsers pre-installed
- [ ] Build container orchestration layer (spin up, execute, tear down)
- [ ] Implement container pooling for parallel execution
- [ ] Set up networking between containers and preview app URLs
- [ ] Implement container cleanup and resource management
- [ ] Build health checks for container readiness
- [ ] Write tests for Docker infrastructure

## 4. Real Browser Test Execution

- [ ] Integrate Playwright for browser automation
- [ ] Build test executor that runs generated E2E tests in Docker containers
- [ ] Support Chrome execution
- [ ] Support Firefox execution
- [ ] Implement parallel test execution across multiple containers
- [ ] Build preview app URL detection from PR (Vercel, Netlify, custom preview URLs)
- [ ] Implement test retry logic for flaky tests
- [ ] Build structured result reporting (per-test pass/fail with details)
- [ ] Implement timeout handling for browser tests
- [ ] Write tests for browser execution layer

## 5. Video Recording

- [ ] Implement video capture during browser test execution
- [ ] Record full test session from start to finish
- [ ] Generate per-test video clips (isolate each test's recording)
- [ ] Implement video compression for storage efficiency
- [ ] Build video storage layer (local for self-hosted, cloud for paid tier)
- [ ] Generate video thumbnails for UI display
- [ ] Link video timestamps to specific test steps/assertions
- [ ] Implement video retention policy (configurable duration)
- [ ] Write tests for video capture pipeline

## 6. Session Replay

- [ ] Capture DOM events during test execution (clicks, inputs, navigation)
- [ ] Capture network requests and responses
- [ ] Capture console logs and errors
- [ ] Build event timeline from captured data
- [ ] Build session replay player component
- [ ] Implement playback speed controls (1x, 2x, 4x)
- [ ] Link replay events to test assertion failures
- [ ] Highlight the exact interaction that caused failure
- [ ] Store replay data alongside test results
- [ ] Write tests for replay data capture

## 7. Test Results API

- [ ] Design test result data model
- [ ] Build API endpoints for test result storage and retrieval
- [ ] Implement test result aggregation (per-PR summary)
- [ ] Build pass/fail/error/skip counters
- [ ] Link test results to PR comments
- [ ] Format test results as GitHub PR comment (markdown table with status)
- [ ] Include video/replay links in PR comments for failed tests
- [ ] Write tests for results API

## 8. Integration with Phase 1

- [ ] Connect test generation to existing PR review flow
- [ ] Run tests after code review completes
- [ ] Include test results in PR comment alongside review findings
- [ ] Add `--test` flag to CLI for triggering test generation + execution
- [ ] Add `--test-only` flag for running tests without code review
- [ ] Update JSON output schema to include test results
- [ ] Write integration tests for full review + test flow
