# RunOwl — Phase 2b Tasks: Platform & Management

## 1. SvelteKit Project Setup ✅

- [x] Initialize SvelteKit project with TypeScript (switched from Next.js)
- [x] Configure dark mode as default theme with light mode toggle, persisted to localStorage
- [x] Set up ESLint, Prettier, svelte-check
- [x] Configure environment variables (`.env.local`, `.env.example`)
- [x] Create base layout with collapsible sidebar navigation (Workspace / Configure / Admin sections)
- [x] CI / demo mode: `USE_MOCK_DATA=true` bypasses Supabase and serves seed data

## 2. Authentication & Accounts ✅

- [x] Set up Supabase Auth (email + GitHub OAuth)
- [x] Implement sign up and sign in flows
- [x] Implement password reset
- [x] Build user profile page (`/app/profile`) — account info, password change, danger zone
- [x] Implement session management via Supabase SSR middleware
- [x] Build API authentication middleware (`locals.safeGetSession()`)

## 3. Diff Viewer ✅

- [x] Build file browser panel (list changed files with status badges: added/modified/deleted)
- [x] Implement file selection and navigation
- [x] Build diff viewer with syntax-highlighted patch hunks
- [x] Implement line number display
- [x] Build text selection within diffs (captures line context for Q&A)
- [x] Implement code highlighting when clicking on citations/findings

## 4. PR Summary Panel ✅

- [x] Build PR metadata display (title, author, branch, commit count)
- [x] Display change statistics (files changed, additions, deletions)
- [x] Show PR description/body
- [x] Show review status indicator (pending, running, complete)
- [x] Report download buttons (Markdown, JSON, PDF via browser print)

## 5. Chat Panel ✅

- [x] Build tabbed interface — Code Review, Flags, Bugs, Tests tabs
- [x] **Code Review tab:** chat input, message display, SSE streaming, conversation history
- [x] **Flags tab:** informational/investigation findings with severity indicators
- [x] **Bugs tab:** critical findings with fix suggestions for P0/P1
- [x] **Tests tab:** "Generate & run tests" CTA with animated progress + re-run button
- [x] AI follow-up suggestion chips (4 chips, context-aware, rotate on refresh)

## 6. PR Loading Flow ✅

- [x] Build PR URL input field with validation
- [x] Implement PR loading with skeleton states
- [x] Handle errors (invalid URL, rate limits)
- [x] Private repo detection: amber banner + inline "Connect GitHub →" prompt
- [x] GitHub App + PAT connect modal triggered on private repo 403/404
- [x] Cache loaded PR data for session

## 7. Layout & Navigation ✅

- [x] Collapsible sidebar sections with chevron toggles, localStorage persistence
- [x] Notification bell with unread badge and dropdown panel
- [x] Onboarding checklist card (3 steps, progress bar, dismissable)
- [x] Responsive layout for smaller screens

## 8. Video & Replay Viewer (UI) ✅

- [x] Build video player component for test failure recordings
- [x] Implement session replay player with timeline
- [x] Build playback controls (play, pause, speed, seek)

## 9. API Layer (Backend for Frontend) ✅

- [x] `POST /api/pr/load` — load PR metadata and files from GitHub API
- [x] `GET /api/pr/file` — fetch file contents
- [x] `POST /api/review/run` — trigger code review (proxies to Python backend)
- [x] `POST /api/review/ask` — Q&A on diffs (SSE streaming)
- [x] `GET /api/review/results/[jobId]` — fetch review results
- [x] `GET /api/reviews` — list past reviews with chart data
- [x] `POST /api/reviews` — save review to Supabase
- [x] `GET /api/tests/suites` — list test suites
- [x] `POST /api/tests/run` — trigger test generation + execution (proxies to Python backend)
- [x] `GET /api/tests/results?suite_id=` — fetch test suite results (mock data + real proxy)
- [x] `GET /api/team/members` — list team members
- [x] `POST /api/team/invite` — invite member
- [x] All routes mock-data capable via `USE_MOCK_DATA=true`

## 10. GitHub Private Repository Integration ✅ (UI layer)

- [x] Integrations page (`/app/integrations`) — full management hub
- [x] GitHub App connection flow (simulated OAuth → repo picker)
- [x] PAT fallback connection flow
- [x] Connected repo list with remove/confirm controls
- [x] Org-level installation nudge banner
- [x] `githubIntegration` store with localStorage persistence
- [x] Inline private-repo detection banner on review page
- [x] Modal auto-triggers on 403/404, review restarts after connect
- [ ] Real GitHub App OAuth token exchange (backend pending)

