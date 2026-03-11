# RunOwl — Brand Strategy Document

## 1. Brand Identity

| Element | Detail |
|---|---|
| **Product Name** | RunOwl |
| **Company** | TBD |
| **Primary Tagline** | "One agent. Reviews, tests, ships." |
| **Secondary Tagline** | "Every PR, reviewed and tested. Automatically." |
| **Brand Voice** | Technical & no-nonsense |
| **Logo Direction** | Owl icon — minimal, geometric, dev-tool aesthetic |

## 2. Positioning

**Category:** AI-powered code review and testing platform

**Positioning Statement:**
RunOwl is an AI agent that reviews code, generates tests, and runs them — all before you merge. Built as an open-source core with a paid cloud tier, it gives small engineering teams enterprise-grade code quality without the overhead.

**Market Position:** Hybrid open-source — free CLI and self-hosted option, paid tiers for deep analysis, testing, dashboards, and team features.

## 3. Target Audience

### Primary: Small Engineering Teams (5–20 devs)
- Shipping fast, limited QA resources
- Need automated review and testing in their PR workflow
- Value open-source, prefer tools they can self-host and inspect
- Budget-conscious but willing to pay for features that save time

### Secondary: Mid-Market Companies (20–100 devs)
- Need team management, dashboards, integrations
- Care about compliance, audit trails, and reporting
- Evaluating build vs buy for QA tooling

### Always Supported: Open-Source Maintainers
- Reviewing external contributions from unknown contributors
- Need security scanning on incoming PRs
- Free tier must be genuinely useful, not a demo

## 4. Brand Voice Guidelines

### Tone: Technical & No-Nonsense
- Lead with what it does, not how it feels
- Use developer language — PRs, diffs, CI/CD, sandbox, severity levels
- No buzzwords, no fluff, no emojis in product copy
- Short sentences. Direct claims. Backed by specifics.

### Examples

**Do:**
- "RunOwl reads your diff, explores the repo, and reports findings with file paths and line numbers."
- "Surface-level security scan on every PR. Deep OWASP analysis on the paid tier."
- "One command: `npx runowl review --url <PR_URL>`"

**Don't:**
- "Supercharge your development workflow with our cutting-edge AI solution!"
- "RunOwl is the ultimate game-changer for modern dev teams."
- "We're passionate about helping developers ship better code."

## 5. Competitive Differentiation

| | RunOwl | CodeRabbit | Canary | AsyncReview |
|---|---|---|---|---|
| Code review | Yes | Yes | No | Yes |
| Test generation | Yes (Phase 2) | No | Yes | No |
| Test execution | Yes (Phase 2) | No | Yes | No |
| Open-source | Core is OSS | No | No | Yes |
| Security analysis | Free (basic) + Paid (deep) | Paid | No | Yes (all free) |
| Architecture review | Paid | No | No | Yes (all free) |
| Self-hostable | Yes | No | Yes (enterprise) | Yes |
| CLI-first | Yes | No | No | Yes |

## 6. Messaging Framework

### Elevator Pitch (10 seconds)
"RunOwl is an AI agent that reviews your PRs, generates tests, and runs them before you merge. Open-source core, paid cloud for teams."

### Short Description (30 seconds)
"RunOwl is an AI-powered code review and testing agent. It plugs into your GitHub PRs, analyzes diffs with recursive reasoning, flags bugs and security issues with severity levels, and — in later releases — auto-generates and runs tests in real browsers. The core is open-source. Deep security, architecture analysis, and team features are on the paid tier."

### Key Messages
1. **For developers:** "One command. Full code review. No config."
2. **For team leads:** "Every PR reviewed and tested before it reaches your queue."
3. **For CTOs:** "Open-source core you can audit. Paid cloud your team can scale on."

## 7. Pricing Positioning

| Tier | Price | Message |
|---|---|---|
| **Free** | $0 | "Full code review. Surface security. Unlimited repos." |
| **Team** | $9/user/month | "Deep security. Architecture analysis. Built for small teams." |
| **Business** | $19/user/month | "Full testing. Dashboards. Priority support." |
| **Enterprise** | Custom | "On-prem. SSO. Audit logs. Your rules." |

## 8. Channel Strategy

### Launch Channels
- GitHub (open-source repo, GitHub Actions marketplace)
- Hacker News / Reddit r/programming / r/devops
- Dev.to / Hashnode technical blog posts
- Twitter/X developer community
- Product Hunt launch

### Ongoing Channels
- Technical blog (SEO — "AI code review," "automated testing," "PR automation")
- YouTube (demo videos, walkthroughs)
- Discord community for users and contributors
- Conference talks / dev meetups

## 9. Brand Assets Needed

- [ ] Logo (owl icon + wordmark)
- [ ] Color palette (dark-mode first, dev-tool aesthetic)
- [ ] Typography (monospace for code, clean sans-serif for UI)
- [ ] Website (runowl.ai or similar)
- [ ] Social media profiles
- [ ] README badges and banners
- [ ] CLI output styling (consistent colors and formatting)
