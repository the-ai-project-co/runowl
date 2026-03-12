# RunOwl — Phase 2a Tasks: Testing Engine

## 1. Test Generation Agent

- [x] Design test generation prompt system
- [x] Build agent that reads PR diffs and generates test cases
- [x] Implement natural language → test code conversion
- [x] Support test framework detection (auto-detect Jest, Pytest, Playwright, etc.)
- [x] Generate unit tests for changed functions
- [x] Generate integration tests for changed API endpoints
- [x] Generate E2E tests for changed user flows
- [x] Map each generated test to the source code it covers
- [x] Build confidence scoring for generated tests (high/medium/low)
- [x] Implement test deduplication (avoid generating tests that already exist)
- [x] Write tests for the test generator

## 2. Sandboxed Test Execution (Deno)

- [x] Extend existing Deno sandbox for test execution
- [x] Build test runner that executes generated unit tests
- [x] Build test runner that executes generated integration tests
- [x] Implement result collection (pass, fail, error, skip)
- [x] Capture stdout/stderr from test runs
- [x] Implement timeout handling per test
- [x] Implement resource limits (memory, CPU)
- [x] Build structured test result output
- [x] Write tests for sandbox test execution

## 3. Docker Infrastructure for Browser Testing

- [x] Design Docker container architecture for browser testing
- [x] Create Dockerfile with Playwright + browsers pre-installed
- [x] Build container orchestration layer (spin up, execute, tear down)
- [x] Implement container pooling for parallel execution
- [x] Set up networking between containers and preview app URLs
- [x] Implement container cleanup and resource management
- [x] Build health checks for container readiness
- [x] Write tests for Docker infrastructure

## 4. Real Browser Test Execution

- [x] Integrate Playwright for browser automation
- [x] Build test executor that runs generated E2E tests in Docker containers
- [x] Support Chrome execution
- [x] Support Firefox execution
- [x] Implement parallel test execution across multiple containers
- [x] Build preview app URL detection from PR (Vercel, Netlify, custom preview URLs)
- [x] Implement test retry logic for flaky tests
- [x] Build structured result reporting (per-test pass/fail with details)
- [x] Implement timeout handling for browser tests
- [x] Write tests for browser execution layer

## 5. Video Recording

- [x] Implement video capture during browser test execution
- [x] Record full test session from start to finish
- [x] Generate per-test video clips (isolate each test's recording)
- [x] Implement video compression for storage efficiency
- [x] Build video storage layer (local for self-hosted, cloud for paid tier)
- [x] Generate video thumbnails for UI display
- [x] Link video timestamps to specific test steps/assertions
- [x] Implement video retention policy (configurable duration)
- [x] Write tests for video capture pipeline

## 6. Session Replay

- [x] Capture DOM events during test execution (clicks, inputs, navigation)
- [x] Capture network requests and responses
- [x] Capture console logs and errors
- [x] Build event timeline from captured data
- [x] Build session replay player component
- [x] Implement playback speed controls (1x, 2x, 4x)
- [x] Link replay events to test assertion failures
- [x] Highlight the exact interaction that caused failure
- [x] Store replay data alongside test results
- [x] Write tests for replay data capture

## 7. Test Results API

- [x] Design test result data model
- [x] Build API endpoints for test result storage and retrieval
- [x] Implement test result aggregation (per-PR summary)
- [x] Build pass/fail/error/skip counters
- [x] Link test results to PR comments
- [x] Format test results as GitHub PR comment (markdown table with status)
- [x] Include video/replay links in PR comments for failed tests
- [x] Write tests for results API

## 8. Integration with Phase 1

- [x] Connect test generation to existing PR review flow
- [x] Run tests after code review completes
- [x] Include test results in PR comment alongside review findings
- [x] Add `--test` flag to CLI for triggering test generation + execution
- [x] Add `--test-only` flag for running tests without code review
- [x] Update JSON output schema to include test results
- [x] Write integration tests for full review + test flow
