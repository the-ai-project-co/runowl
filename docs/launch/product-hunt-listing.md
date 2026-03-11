# RunOwl — Product Hunt Listing

## Tagline

AI code review that actually reads your code — not just the diff

## Description (260 characters max)

RunOwl is an open-source AI agent that reviews GitHub PRs, finds bugs and security issues with severity levels, and posts results as PR comments. Free tier + paid deep analysis. Works in 30 seconds with `npx runowl review --url <pr>`.

## Full Description

**RunOwl reviews your PRs so you don't have to review them blind.**

Most AI code review tools scan your diff for obvious patterns. RunOwl actually *reasons* about your code — fetching related files, tracing call chains, and building context before flagging anything.

**How it works:**
RunOwl uses a Recursive Reasoning Loop: read the diff → decide what to fetch → read related files in a sandboxed environment → refine the analysis → repeat. It cites exact file paths and line numbers. If a line isn't in the diff, RunOwl won't fabricate a finding for it.

**What it finds (free):**
- Hardcoded secrets and API keys
- SQL injection (f-strings, string concatenation in queries)
- XSS (innerHTML, dangerouslySetInnerHTML)
- Missing auth on new endpoints
- Exposed environment variables
- Unpinned dependencies

**What it finds (paid — Team tier):**
- Full OWASP Top 10 (IDOR, weak crypto, command injection, JWT flaws, CORS wildcards)
- SOLID violations (god objects, fat interfaces, DI violations)
- Race conditions and supply chain risks

**Severity that matters:**
P0 (critical) and P1 (high) findings block the GitHub Check Run. The LLM can't under-classify a hardcoded AWS key — our rule-based reclassifier promotes it automatically.

**Get started in 30 seconds:**
```
npx runowl review --url https://github.com/owner/repo/pull/42
```

Open-source (MIT). Self-hostable. [github.com/the-ai-project-co/RunOwl](https://github.com/the-ai-project-co/RunOwl)

## Topics / Tags

developer-tools, open-source, ai, code-review, github, security, devops

## First Comment (Maker's Comment)

Hey PH! 👋

I'm one of the founders of RunOwl. We built this because we were frustrated with code review tools that either:

1. Pattern-match against your code without reading it, or
2. Use LLMs but hallucinate file paths and line numbers that don't exist in the PR

RunOwl actually reads your code. It fetches related files, traces how functions are called, and builds context before flagging anything. Every finding cites an exact line in the diff — if the line isn't there, the finding isn't made.

The free tier is genuinely useful: hardcoded secrets, SQL injection, XSS, missing auth, unpinned dependencies. The paid Team tier adds full OWASP analysis and SOLID checks.

We'd love feedback on:
- False positive rate (are we flagging things that aren't issues?)
- False negative rate (are we missing things you'd expect to catch?)
- Any language/framework we should prioritise support for

Try it on any public GitHub PR: `npx runowl review --url <pr-url>`

Happy to answer any questions below!

## Screenshots / Assets Needed

1. Terminal screenshot: `npx runowl review` with Rich-formatted output showing findings table
2. PR comment screenshot: formatted markdown review comment with severity badges
3. GitHub Check Run screenshot: pass/fail check on a PR
4. Architecture diagram: RLM loop visualization

## Pricing

- **Free:** Core review, surface security, Q&A, webhook
- **Team:** $29/seat/month — deep OWASP, SOLID analysis, Check Runs
- **Business:** $79/seat/month — priority support, SSO
- **Enterprise:** Custom — self-hosted, audit logs, SCIM
