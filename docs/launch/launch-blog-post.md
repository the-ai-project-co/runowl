# Introducing RunOwl — AI Code Review That Actually Finds Bugs

*March 2026*

---

We've been building RunOwl for the past few months, and today we're shipping the first public release.

Here's the short version: **RunOwl is an AI agent that reviews your GitHub PRs, flags bugs and security issues with severity levels, and posts its findings as PR comments — automatically, every time a PR opens.**

---

## The problem we're solving

Code review is broken in two ways.

**First:** Most AI code review tools today are glorified linters. They scan for style issues, obvious patterns, and surface-level problems. They don't reason about your code — they pattern-match against it.

**Second:** The tools that do use LLMs tend to hallucinate. They invent file paths that don't exist, cite line numbers from files they never read, and produce findings that refer to code that isn't in the diff.

RunOwl does neither of those things.

---

## How RunOwl works

RunOwl uses a **Recursive Reasoning Loop (RLM)** — a tight loop where the agent:

1. Reads the PR diff and PR description
2. Reasons about what it sees
3. Decides which files to fetch, search, or explore for more context
4. Executes those tool calls in a sandboxed environment
5. Refines its analysis
6. Repeats until it has a complete picture

The key insight: **code review requires context beyond the diff.** A bug in a PR often only makes sense when you see how the function being modified is called elsewhere. RunOwl can fetch those callers, inspect the interface, and reason about the full picture.

All tool execution happens in a **Deno sandbox** with strict permissions — no network access, no file writes, no shell access. The agent can only read your code via the GitHub API.

---

## What it finds

**Free tier (open-source):**
- Hardcoded secrets and API keys
- SQL injection patterns (f-strings, string concatenation in queries)
- XSS vulnerabilities (innerHTML, dangerouslySetInnerHTML, render_template_string)
- Missing authentication on new endpoints
- Exposed environment variables in logs or responses
- Unpinned dependencies

**Team tier (paid):**
- Full OWASP Top 10 — broken access control (IDOR), cryptographic failures (MD5/SHA1/ECB mode, hardcoded IVs), command injection, NoSQL injection, template injection, JWT vulnerabilities, CORS wildcards, debug mode in production
- SOLID principle violations — god objects, open/closed violations, LSP breakage, fat interfaces, hardcoded dependencies
- Code smells — long methods, deep nesting, feature envy
- Race conditions — TOCTOU patterns, unsynchronized shared state
- Supply chain risks — typosquatting package names, eval of network content

Every finding has:
- A severity level: **P0** (critical, blocks merge) through **P3** (low, informational)
- A citation: the exact file and line number in the diff
- A fix suggestion for P0 and P1 findings

---

## Severity that means something

We classify findings into four severity levels — and we enforce them:

- **P0 — Critical:** Security vulnerabilities, data loss risks. Blocks merge.
- **P1 — High:** Bugs that will cause production failures. Blocks merge.
- **P2 — Medium:** Issues worth fixing but not urgent. Does not block merge.
- **P3 — Low:** Style, architecture suggestions. Informational.

The agent's severity classifications are verified by a rule-based reclassifier. If an LLM calls a hardcoded AWS key "P2 — medium severity", our classifier promotes it to P0 automatically. The LLM can't under-classify critical issues.

---

## Getting started in 30 seconds

```bash
npx runowl review --url https://github.com/owner/repo/pull/42
```

You need:
- Node.js 18+
- Python 3.12+
- A Gemini API key (`GEMINI_API_KEY` in your environment)

That's it. For private repos, add a `GITHUB_TOKEN`.

---

## Webhook integration

For teams, RunOwl can auto-review every PR:

```bash
# Start the server
uv run uvicorn main:app --host 0.0.0.0 --port 8000

# Point your GitHub webhook at:
# https://your-server.com/webhook/github
```

When a PR opens:
1. RunOwl creates a GitHub Check Run (shown in the PR UI)
2. Runs the full review
3. Posts findings as a PR comment
4. Updates the Check Run — green if no blocking issues, red if P0/P1 found

---

## Open-source

RunOwl's core is MIT licensed. The full source is at [github.com/the-ai-project-co/RunOwl](https://github.com/the-ai-project-co/RunOwl).

The surface security checks, code review agent, Q&A engine, GitHub integration, and CLI are all free. Deep OWASP analysis and SOLID checks are paid (Team tier) — that's how we fund continued development.

---

## What's next

This is v0.1.0 — the review engine. Here's what's coming:

- **Phase 2:** Test generation and execution — RunOwl generates and runs tests for the code it reviews
- **Phase 3:** Real browser testing with Playwright — spins up a preview and tests it live
- **Phase 4:** Slack integration, Linear/Jira issue creation, GitLab/Bitbucket support
- **Phase 5:** Self-hosted enterprise deployment with SSO and audit logs

---

Try it: `npx runowl review --url <your-pr>`

Docs: [runowl.ai](https://runowl.ai)

GitHub: [github.com/the-ai-project-co/RunOwl](https://github.com/the-ai-project-co/RunOwl)

If you hit a bug or have a feature request, [open an issue](https://github.com/the-ai-project-co/RunOwl/issues).
