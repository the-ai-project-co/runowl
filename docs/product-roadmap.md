# RunOwl — Product Roadmap

## Overview

RunOwl is an AI agent that reviews code, generates tests, and runs them before merge. Built as an open-source core with paid cloud tiers.

**Tech Stack:** Python (FastAPI) · Next.js (React) · Gemini · Deno + Docker

---

## Phase 1 — MVP: AI Code Review

**Goal:** Ship the core code review engine. Establish the open-source project and freemium split.

### Free / Open-Source
- AI-powered PR code review with recursive reasoning
- Interactive Q&A on PR diffs
- Severity-classified findings (P0–P3)
- Surface-level security analysis (basic checks)
- CLI tool (`npx runowl`)
- GitHub PR integration (trigger on PR open, post results as comments)

### Paid / Cloud
- Deep security vulnerability detection (full OWASP checklist — XSS, injection, JWT, crypto, race conditions, supply chain)
- SOLID / architecture analysis (design patterns, code smells, god objects, dependency inversion)

---

## Phase 2a — Testing Engine

**Goal:** Add test generation and execution capabilities.

- Auto test generation from code diffs
- Test execution in sandboxed environments (Deno)
- Test execution in real browsers (Docker)
- Video recordings of test failures
- Session replay for debugging

---

## Phase 2b — Platform & Management

**Goal:** Build the web UI and team collaboration layer.

- Web UI dashboard (diff viewer + chat + bugs panel)
- Team management & role-based access
- Test suite management (versioning, drafts, rollback)

---

## Phase 3 — Intelligence & Ecosystem

**Goal:** Make RunOwl composable and smarter over time.

- Skill/agent integration (works inside Claude, Cursor, Codex, etc.)
- JSON/Markdown output for CI/CD pipelines
- Real-time reporting with screenshots and logs
- AI-generated follow-up suggestions (smart next questions)
- Regression detection across PRs (track patterns over time)

---

## Phase 4 — Integrations & Scale

**Goal:** Expand platform reach and third-party ecosystem.

### Integrations
- Slack notifications
- Linear issue creation from findings
- Jira integration
- GitLab support
- Bitbucket support

### Platform Expansion
- Multi-model support (Gemini, Claude, GPT)
- Custom review rules (team-defined checklists)
- PR analytics dashboard (merge velocity, bug trends, code quality over time)
- Public REST API for third-party integrations
- Monorepo support (scoped reviews per package/service)

---

## Phase 5 — Enterprise

**Goal:** Enterprise-grade deployment and compliance.

- On-premises / self-hosted deployment
- SSO / SAML authentication
- Audit logs and compliance reporting
- Multi-environment support (prod, staging, dev)

---

## Pricing Tiers

| Tier | Price | Availability |
|---|---|---|
| Free | $0 | Phase 1 |
| Team | $9/user/month | Phase 1 (paid features) |
| Business | $19/user/month | Phase 2b |
| Enterprise | Custom | Phase 5 |

## Target Audience (in order)

1. Small engineering teams (5–20 devs)
2. Mid-market companies (20–100 devs)
3. Open-source maintainers (always supported via free tier)
