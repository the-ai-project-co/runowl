# RunOwl

> One agent. Reviews, tests, ships.

RunOwl is an open-source AI agent that reviews your GitHub PRs — flags bugs, security vulnerabilities, and architecture issues with severity levels, posts findings as PR comments, and blocks merges when critical issues are detected.

**Open-source core · Paid extensions in [runowl-paid](https://github.com/the-ai-project-co/runowl-paid)**

---

## Quick Start

```bash
npx runowl review --url https://github.com/owner/repo/pull/42
```

That's it. RunOwl fetches the PR diff, reasons over it with Gemini, and prints a structured review.

---

## Features

| Feature | Free | Team | Business | Enterprise |
|---|:---:|:---:|:---:|:---:|
| AI code review (P0–P3 severity) | ✅ | ✅ | ✅ | ✅ |
| Interactive Q&A on PR diffs | ✅ | ✅ | ✅ | ✅ |
| Surface security checks | ✅ | ✅ | ✅ | ✅ |
| GitHub webhook auto-review | ✅ | ✅ | ✅ | ✅ |
| Deep OWASP security analysis | — | ✅ | ✅ | ✅ |
| SOLID / architecture analysis | — | ✅ | ✅ | ✅ |
| GitHub Check Runs (pass/fail) | — | ✅ | ✅ | ✅ |
| Team management & RBAC | — | ✅ | ✅ | ✅ |
| Regression detection | — | ✅ | ✅ | ✅ |
| Slack / Linear / Jira integrations | — | — | ✅ | ✅ |
| SSO / SAML | — | — | ✅ | ✅ |
| Audit logging | — | — | — | ✅ |
| SCIM provisioning | — | — | — | ✅ |
| Self-hosted / on-premises | — | — | — | ✅ |

---

## CLI Usage

### Review a PR

```bash
# Basic review
npx runowl review --url https://github.com/owner/repo/pull/42

# With deep security + SOLID analysis (paid)
npx runowl review --url https://github.com/owner/repo/pull/42 --expert

# Output as JSON (for CI pipelines)
npx runowl review --url https://github.com/owner/repo/pull/42 --output json

# Post the review as a GitHub PR comment
npx runowl review --url https://github.com/owner/repo/pull/42 --submit

# Ask a specific question instead of full review
npx runowl review --url https://github.com/owner/repo/pull/42 --question "Any SQL injection risks?"

# Suppress progress output (results only)
npx runowl review --url https://github.com/owner/repo/pull/42 --quiet
```

### Interactive Q&A

```bash
npx runowl ask --url https://github.com/owner/repo/pull/42
```

Session commands: `quit`, `reset`, `history`, `files`, `info`

### All flags

```
runowl review
  -u, --url <url>         GitHub PR URL (required)
  -q, --question <q>      Ask a specific question
      --expert            Deep security + SOLID analysis (paid)
  -o, --output <fmt>      text (default) | markdown | json
      --quiet             Results only, no progress
      --submit            Post as GitHub PR comment
  -m, --model <model>     Gemini model
  -V, --version           Version
  -h, --help              Help
```

---

## GitHub Webhook Setup

RunOwl can auto-review every PR the moment it opens.

1. **Start the server**

   ```bash
   uv run uvicorn main:app --host 0.0.0.0 --port 8000
   ```

2. **Configure the GitHub webhook**

   - Payload URL: `https://your-server.com/webhook/github`
   - Content type: `application/json`
   - Secret: set `GITHUB_WEBHOOK_SECRET` in your `.env`
   - Events: **Pull requests**

3. **What happens**

   - PR opened / pushed to → RunOwl reviews it
   - Posts findings as a PR comment
   - Creates a GitHub Check Run (pass if no blocking issues, fail if P0/P1 found)

---

## Environment Variables

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | **Yes** | Google Gemini API key |
| `GITHUB_TOKEN` | Recommended | GitHub PAT — required for private repos, increases rate limits |
| `GITHUB_WEBHOOK_SECRET` | Webhook only | HMAC secret for validating webhook payloads |
| `RUNOWL_API_KEY` | Paid features | RunOwl license key — unlocks Team tier and above |
| `RUNOWL_TIER` | Override | `free` · `team` · `business` · `enterprise` |

---

## Architecture

```
npx runowl
    └── Node.js CLI (cli/)
            └── python -m runowl.cli
                    ├── ReviewAgent          # orchestrates full review
                    │   ├── GitHubClient     # fetches PR metadata + diffs
                    │   ├── ReasoningEngine  # Gemini RLM loop
                    │   │   └── Deno sandbox # safe agent code execution
                    │   └── FindingParser    # structured P0–P3 output
                    ├── SecurityScanner      # surface + deep OWASP checks
                    ├── SOLIDScanner         # architecture analysis
                    └── QAEngine             # interactive Q&A
```

**Recursive Reasoning Loop (RLM):** The agent reasons → generates a Gemini tool call → executes it via `GitHubClient` → refines. Up to 20 iterations, 15 LLM calls. All agent tool calls run in a Deno sandbox with strict permissions — no network access, no file writes, no shell.

---

## Repository Structure

This is the **free / open-source** repository. The RunOwl workspace contains three repos:

```
RunOwl/                    ← workspace root (no git)
├── runowl/                ← this repo — free core (MIT)
├── runowl-paid/           ← private — paid extensions (Team / Business / Enterprise)
└── runowl-website/        ← SvelteKit marketing site + docs
```

### `runowl/` layout

```
runowl/
├── src/
│   ├── architecture/      # SOLID / architecture analysis (stubs in free tier)
│   ├── freemium/          # Tier detection, feature flags, upgrade prompts
│   ├── github/            # GitHub API client, diff parser, models
│   ├── qa/                # Interactive Q&A engine
│   ├── reasoning/         # Gemini RLM loop, prompts, context builder
│   ├── review/            # Review agent, finding parser, severity, formatter
│   ├── runowl/            # CLI entry point (python -m runowl.cli)
│   ├── sandbox/           # Deno sandbox runner + bootstrap
│   ├── security/          # Surface checks (free) + deep check stubs (paid)
│   ├── webhook/           # GitHub webhook receiver + Check Runs
│   ├── config.py          # Settings (pydantic-settings)
│   └── main.py            # FastAPI app
├── cli/                   # TypeScript npm package (npx runowl)
├── tests/                 # pytest test suite
├── docs/
│   ├── phases/            # Phase 1–3 task lists (free portions)
│   ├── launch/            # Blog post, launch posts, Product Hunt listing
│   └── milestones.md      # Phase 1–4 milestone tracker (free portions)
├── CONTRIBUTING.md
├── INSTALLATION.md
├── CHANGELOG.md
└── pyproject.toml
```

---

## Development

See [INSTALLATION.md](INSTALLATION.md) for full setup instructions.

```bash
# Clone
git clone https://github.com/the-ai-project-co/runowl.git
cd runowl

# Install Python deps
uv sync --extra dev

# Run tests
uv run pytest

# Lint + format
uv run ruff check .
uv run black --check .

# Build CLI
cd cli && npm install && npm run build
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT
