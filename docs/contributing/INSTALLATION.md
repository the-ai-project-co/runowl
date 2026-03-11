# Installation

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12+ | 3.14 works fine |
| uv | 0.10+ | Recommended package manager |
| Node.js | 18+ | Required for `npx runowl` CLI |
| Deno | 2.x | Required for sandbox execution |
| Git | any | |

---

## Option 1 — npx (no install)

```bash
npx runowl review --url https://github.com/owner/repo/pull/42
```

Requires Node.js 18+ and Python 3.12+ on `PATH`.

---

## Option 2 — Global npm install

```bash
npm install -g runowl
runowl review --url https://github.com/owner/repo/pull/42
```

---

## Option 3 — Self-hosted (development)

### 1. Install uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Clone and install

```bash
git clone https://github.com/the-ai-project-co/RunOwl.git
cd RunOwl
uv sync --extra dev
```

### 3. Install Deno

```bash
# macOS / Linux
curl -fsSL https://deno.land/install.sh | sh

# Windows (PowerShell)
irm https://deno.land/install.ps1 | iex
```

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GITHUB_TOKEN=ghp_your_token_here         # optional but recommended
```

Get a Gemini API key at https://aistudio.google.com/

### 5. Build the CLI

```bash
cd cli
npm install
npm run build
cd ..
```

### 6. Run

```bash
# Using the Python CLI directly
uv run python -m runowl.cli review --url https://github.com/owner/repo/pull/42

# Or start the webhook server
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Environment Variables Reference

Copy `.env.example` to `.env` and fill in your values.

### Required

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key. Get one at https://aistudio.google.com/ |

### Recommended

| Variable | Description |
|---|---|
| `GITHUB_TOKEN` | GitHub Personal Access Token. Required for private repos. Increases API rate limits from 60 to 5,000 req/hr. Needs `repo` scope for private repos, `public_repo` for public only. |

### Webhook server

| Variable | Description |
|---|---|
| `GITHUB_WEBHOOK_SECRET` | Random secret string used to verify GitHub webhook payloads via HMAC-SHA256. Generate with `openssl rand -hex 32`. |

### Paid features

| Variable | Description |
|---|---|
| `RUNOWL_API_KEY` | RunOwl license key. Unlocks Team tier features (deep security, SOLID analysis, Check Runs). Get one at https://runowl.ai/pricing |
| `RUNOWL_TIER` | Explicit tier override: `free`, `team`, `business`, `enterprise`. |

### Server configuration

| Variable | Default | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `ENV` | `development` | `development` or `production` |

---

## GitHub App Setup (for webhooks)

For team / organisation use, configure a GitHub App instead of a personal token:

1. Create a GitHub App at `https://github.com/settings/apps/new`
2. Set **Webhook URL** to `https://your-server.com/webhook/github`
3. Set **Webhook secret** (same value as `GITHUB_WEBHOOK_SECRET`)
4. Enable **Pull requests** → Read & write permission
5. Enable **Checks** → Read & write permission
6. Subscribe to **Pull request** events
7. Install the app on your repositories
8. Download the private key and set:
   ```env
   GITHUB_APP_ID=123456
   GITHUB_APP_PRIVATE_KEY_PATH=/path/to/private-key.pem
   ```

---

## Verifying the Installation

```bash
# Check the server is running
curl http://localhost:8000/health
# → {"status":"ok","version":"0.1.0"}

# Check your tier
curl http://localhost:8000/license/tier
# → {"tier":"free","features":[...],"is_paid":false}

# Run the test suite
uv run pytest
```
