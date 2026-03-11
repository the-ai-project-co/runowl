# RunOwl — Launch Posts

## Hacker News — Show HN

**Title:**
Show HN: RunOwl – Open-source AI agent that reviews PRs by actually reading your code

**Post body:**

I got tired of AI code review tools that pattern-match against your diff without reading your code, so I built RunOwl.

The core insight: good code review requires context beyond the diff. A bug often only makes sense when you see how the modified function is called elsewhere. RunOwl can fetch those callers.

**How it works:**
It uses a Recursive Reasoning Loop — read the diff, decide what else to fetch, read related files via GitHub API in a Deno sandbox (no network, no writes, whitelisted tools only), refine analysis, repeat. Up to 20 iterations.

Every finding cites an exact file and line number from the diff. If the line isn't in the diff, the finding isn't made.

**What it catches (free):**
- Hardcoded secrets, SQL injection (f-strings/concat), XSS, missing auth on endpoints, exposed env vars, unpinned dependencies

**Paid (Team tier):**
- Full OWASP Top 10, JWT flaws, weak crypto, SOLID violations, race conditions, supply chain risks

**Severity is enforced:**
P0/P1 findings block the GitHub Check Run. A rule-based reclassifier prevents the LLM from under-classifying a hardcoded AWS key as "P2 medium".

**Try it:**
```bash
npx runowl review --url https://github.com/owner/repo/pull/42
```

Needs: Node 18+, Python 3.12+, `GEMINI_API_KEY` env var.

Source: https://github.com/the-ai-project-co/RunOwl (MIT)

Happy to answer questions about the architecture, the sandbox design, or the reasoning loop.

---

## Reddit — r/programming

**Title:**
RunOwl: open-source AI agent that reviews GitHub PRs — actually reads your code, not just the diff

**Post:**

I built an open-source AI code review tool that works differently from the others.

Most tools scan your diff for obvious patterns. RunOwl uses a reasoning loop: it reads the PR, decides which related files to fetch, reads them via GitHub API (in a sandboxed Deno process — no network/shell/file writes), then refines its analysis. Rinse and repeat.

The result: it finds things that require context. Missing ownership checks when fetching objects by ID. JWT tokens encoded without expiry. Functions being called with wrong argument order across file boundaries.

**Free:**
- Hardcoded secrets, SQL injection, XSS, missing auth on new routes, exposed env vars, unpinned deps

**Paid (Team tier, $29/seat/mo):**
- Full OWASP Top 10, SOLID principle violations, race conditions, supply chain analysis

**Get started:**
```bash
npx runowl review --url <github-pr-url>
```

GitHub: https://github.com/the-ai-project-co/RunOwl

---

## Reddit — r/netsec

**Title:**
Open-source tool for automated security review of GitHub PRs — OWASP Top 10, JWT, crypto, race conditions

**Post:**

Sharing a security-focused open-source tool I built: RunOwl.

It reviews GitHub PRs for security issues — free tier covers the obvious stuff, paid tier goes deeper.

**Free (regex-based, runs on diff `+` lines only):**
- Hardcoded secrets (passwords, API keys, tokens, JWT secrets)
- SQL injection (f-strings, string concatenation, % formatting in queries)
- XSS (innerHTML, dangerouslySetInnerHTML, render_template_string)
- Missing auth decorators on new endpoints
- Secrets logged or returned in API responses
- Unpinned dependency versions

**Paid — full OWASP coverage:**
- A01 Broken Access Control: IDOR patterns, missing `.filter(user=request.user)`
- A02 Cryptographic Failures: MD5/SHA1, DES/ECB mode, hardcoded IVs, non-crypto random for secrets
- A03 Injection: command injection (os.system, subprocess with user input), NoSQL injection, template injection
- A05 Misconfiguration: CORS wildcards, debug=True in production
- A07 Auth Failures: JWT `none` algorithm, `verify=False`, weak secrets, missing `exp` claim, session fixation
- Race conditions: TOCTOU patterns, unsynchronized shared state mutations
- Supply chain: typosquatting package names (requets, djang, etc.), eval of network-fetched content

All checks scan only added lines (`+` in the diff) — no false positives from existing code.

GitHub: https://github.com/the-ai-project-co/RunOwl

---

## Twitter / X Thread

**Tweet 1:**
Shipping RunOwl today — open-source AI that reviews GitHub PRs.

Not pattern matching. Not hallucinating file paths. Actually reading your code.

npx runowl review --url <pr>

🧵

**Tweet 2:**
Most AI code review tools scan your diff and call it done.

RunOwl uses a reasoning loop: read diff → decide what to fetch → read related files → refine → repeat.

It can find bugs that only make sense when you see the call sites.

**Tweet 3:**
Every finding cites an exact line in the diff.

If the line isn't in the diff, the finding doesn't get made.

No hallucinated file paths. No invented line numbers.

**Tweet 4:**
Severity is enforced by a rule-based reclassifier.

If the LLM says a hardcoded AWS key is "P2 medium", the reclassifier promotes it to P0 automatically.

The LLM can't under-classify critical issues.

**Tweet 5:**
Free tier:
- Hardcoded secrets
- SQL injection
- XSS
- Missing auth
- Unpinned deps

Paid (Team):
- Full OWASP Top 10
- SOLID violations
- Race conditions
- Supply chain

**Tweet 6:**
It also auto-reviews PRs via GitHub webhook.

PR opens → Check Run created → review runs → findings posted as comment → Check Run turns green or red.

**Tweet 7:**
Open-source, MIT licensed.

github.com/the-ai-project-co/RunOwl

Try it on any public PR:
npx runowl review --url https://github.com/owner/repo/pull/42

---

## LinkedIn Post

**RunOwl — AI code review that actually reads your code**

Today we're launching RunOwl: an open-source AI agent that reviews GitHub pull requests, finds bugs and security issues with severity levels, and posts results as PR comments.

The difference from other tools: RunOwl uses a reasoning loop. It reads the PR diff, decides which related files to fetch for context, reads them via a sandboxed GitHub API connection, and refines its analysis. It can find issues that only make sense when you see how the code fits together — not just what changed.

Every finding cites an exact file and line in the diff. Severity is enforced: P0 and P1 findings block the GitHub Check Run.

**Free:** Hardcoded secrets, SQL injection, XSS, missing authentication, exposed env vars, unpinned dependencies.

**Team tier ($29/seat/mo):** Full OWASP Top 10, SOLID principle violations, race conditions, supply chain analysis.

**Get started in 30 seconds:**
```
npx runowl review --url <your-github-pr-url>
```

Open-source (MIT): github.com/the-ai-project-co/RunOwl

We'd love feedback from engineering teams — especially on false positive rate and what security checks you'd want to see added.
