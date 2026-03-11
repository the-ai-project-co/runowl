# RunOwl — Phase 2b Tasks: Platform & Management

## 1. Next.js Project Setup

- [ ] Initialize Next.js project with TypeScript
- [ ] Set up Tailwind CSS
- [ ] Configure dark mode as default theme
- [ ] Set up component library (shadcn/ui or similar)
- [ ] Set up ESLint and Prettier
- [ ] Configure environment variables
- [ ] Set up CI pipeline for frontend (lint, type-check, test)
- [ ] Create base layout with navigation

## 2. Authentication & Accounts

- [ ] Set up authentication provider (Clerk, NextAuth, or custom)
- [ ] Implement sign up flow (email, GitHub OAuth)
- [ ] Implement sign in flow
- [ ] Implement password reset
- [ ] Build user profile page
- [ ] Implement session management
- [ ] Build API authentication middleware
- [ ] Write tests for auth flows

## 3. Diff Viewer

- [ ] Build file browser panel (list changed files with status badges)
- [ ] Implement file selection and navigation
- [ ] Build split-pane diff viewer with syntax highlighting
- [ ] Support unified and side-by-side diff views
- [ ] Implement line number display
- [ ] Build text selection within diffs (capture line numbers and context)
- [ ] Implement code highlighting when clicking on citations/findings
- [ ] Build collapsible unchanged code sections
- [ ] Write tests for diff viewer component

## 4. PR Summary Panel

- [ ] Build PR metadata display (title, author, branch, commit count)
- [ ] Display change statistics (files changed, insertions, deletions)
- [ ] Show PR description/body
- [ ] Build collapsible/resizable panel
- [ ] Show review status indicator (pending, running, complete)
- [ ] Display test execution status (if tests were run)
- [ ] Write tests for summary panel

## 5. Chat Panel

- [ ] Build tabbed interface (Code Review, Flags, Bugs)
- [ ] **Code Review tab:**
  - [ ] Chat input with send button
  - [ ] Message display (user questions + AI responses)
  - [ ] Support code selection context in questions
  - [ ] Real-time streaming of AI responses (SSE)
  - [ ] Conversation history within session
- [ ] **Flags tab:**
  - [ ] Display informational and investigation findings
  - [ ] Badge with finding count
  - [ ] Click finding → navigate to code location
  - [ ] Severity indicators per finding
- [ ] **Bugs tab:**
  - [ ] Display critical bug findings
  - [ ] Red badge with bug count
  - [ ] Click bug → navigate to code location
  - [ ] Show fix suggestions for P0/P1 bugs
- [ ] Write tests for chat panel

## 6. PR Loading Flow

- [ ] Build PR URL input field
- [ ] Implement PR loading with progress indicator
- [ ] Build loading skeleton states
- [ ] Handle errors (invalid URL, private repo without token, rate limits)
- [ ] Cache loaded PR data for session
- [ ] Write tests for loading flow

## 7. Layout & Responsiveness

- [ ] Build resizable horizontal divider (between diff and chat panels)
- [ ] Build resizable vertical divider (between PR summary and diff viewer)
- [ ] Set min/max width constraints for panels
- [ ] Implement responsive layout for smaller screens
- [ ] Build keyboard shortcuts for common actions
- [ ] Write tests for layout behavior

## 8. Video & Replay Viewer (UI)

- [ ] Build video player component for test failure recordings
- [ ] Implement session replay player with timeline
- [ ] Build playback controls (play, pause, speed, seek)
- [ ] Show network requests panel alongside replay
- [ ] Show console logs panel alongside replay
- [ ] Link replay to specific test assertion that failed
- [ ] Write tests for video/replay viewer

## 9. API Layer (Backend for Frontend)

- [ ] Design API routes for web UI
- [ ] `POST /api/pr/load` — load PR metadata and files
- [ ] `GET /api/pr/file` — fetch file contents
- [ ] `POST /api/review/run` — trigger code review
- [ ] `POST /api/review/ask` — Q&A on diffs
- [ ] `GET /api/review/results` — fetch review results
- [ ] `GET /api/tests/suites` — list test suites
- [ ] `POST /api/tests/run` — trigger test execution
- [ ] `GET /api/tests/results` — fetch test results
- [ ] `GET /api/team/members` — list team members
- [ ] `POST /api/team/invite` — invite member
- [ ] Implement request validation and error handling
- [ ] Write API tests

