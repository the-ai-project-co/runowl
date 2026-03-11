# Contributing to RunOwl

Thank you for your interest in contributing. This document covers how to set up your development environment, the code standards we follow, and the PR process.

---

## Development Setup

```bash
git clone https://github.com/the-ai-project-co/RunOwl.git
cd RunOwl
uv sync --extra dev
cp .env.example .env   # fill in GEMINI_API_KEY at minimum
```

See [INSTALLATION.md](INSTALLATION.md) for full prerequisites.

---

## Project Structure

```
RunOwl/
├── src/                    # Python source (src layout)
│   ├── architecture/       # SOLID / architecture analysis (paid)
│   ├── freemium/           # Feature flags, tier detection, upgrade prompts
│   ├── github/             # GitHub API client, models, diff parser
│   ├── qa/                 # Interactive Q&A engine
│   ├── reasoning/          # Gemini RLM loop, prompts, context builder
│   ├── review/             # Review agent, finding parser, severity, formatter
│   ├── runowl/             # CLI entry point (python -m runowl.cli)
│   ├── sandbox/            # Deno sandbox runner + bootstrap
│   ├── security/           # Surface + deep security checks
│   ├── webhook/            # GitHub webhook receiver + Check Runs
│   ├── config.py           # Settings (pydantic-settings)
│   └── main.py             # FastAPI app
├── cli/                    # TypeScript npm package (npx runowl)
│   └── src/
│       ├── cli.ts          # Entry point
│       ├── args.ts         # Argument parser
│       ├── runner.ts       # Python process spawner
│       ├── review.ts       # review command
│       └── ask.ts          # ask command
├── tests/                  # pytest test suite (mirrors src/ structure)
├── docs/                   # Product docs, roadmaps, milestones
├── pyproject.toml
└── CHANGELOG.md
```

---

## Running Tests

```bash
# All tests
uv run pytest

# Single module
uv run pytest tests/test_security/

# With coverage
uv run pytest --cov=src --cov-report=term-missing

# Verbose
uv run pytest -v
```

All tests must pass before a PR is merged. Tests run automatically on every push via GitHub Actions.

---

## Code Standards

### Python

- **Formatter:** black (`line-length = 100`)
- **Linter:** ruff (`select = ["E", "F", "I", "N", "W", "UP"]`)
- **Types:** all new code must have type annotations; mypy strict mode
- **Style:**
  - `src/` layout — all packages live under `src/`
  - Prefer `dataclasses` or `pydantic` models over raw dicts
  - Async throughout — use `async def` for all I/O
  - No global mutable state
  - Tests use `pytest` — no `unittest.TestCase` unless required

```bash
# Format
uv run black .

# Lint (auto-fix where possible)
uv run ruff check . --fix

# Type check
uv run mypy src/
```

### TypeScript (CLI)

- **Formatter/linter:** TypeScript strict mode
- Node.js ESM modules (`"type": "module"`)
- No `any` unless unavoidable

```bash
cd cli
npm run build   # compiles and type-checks
```

---

## Writing Tests

- Every new module needs a corresponding test file in `tests/`
- Tests go in the appropriate subdirectory: `tests/test_security/`, `tests/test_review/`, etc.
- Use `pytest` fixtures for shared setup
- Mock external APIs (`GitHubClient`, Gemini) — never make real network calls in tests
- Name test classes `TestSomething`, test functions `test_does_something`
- Aim for one assertion per test where practical

Example:

```python
class TestMyFeature:
    def test_detects_issue(self) -> None:
        diff = _diff("src/app.py", ["suspicious_line()"])
        hits = check_my_feature(diff)
        assert hits

    def test_safe_case_not_flagged(self) -> None:
        diff = _diff("src/app.py", ["safe_line()"])
        assert not check_my_feature(diff)
```

---

## Pull Request Process

1. **Fork** the repo and create a branch from `main`:
   ```bash
   git checkout -b feat/my-feature
   ```

2. **Write code and tests.** All tests must pass:
   ```bash
   uv run pytest
   uv run ruff check .
   uv run black --check .
   ```

3. **Open a PR** against `main` with:
   - A clear title describing the change
   - A description of *what* changed and *why*
   - Screenshots or example output if applicable

4. **PR review:** a maintainer will review within 48 hours. Address feedback with new commits (not force-pushes) so the review history is preserved.

5. **Merge:** once approved and CI is green, a maintainer will squash-merge.

---

## Adding a New Security Check

1. Add your check function to `src/security/checks.py` (surface) or `src/security/deep_checks.py` (paid)
2. Add a new `SecurityCheckType` to `src/security/models.py` if needed
3. Register the check in `run_surface_scan()` or `run_deep_scan()`
4. Write tests in `tests/test_security/test_checks.py` or `test_deep_checks.py`

Template:

```python
_MY_PATTERN = re.compile(r"...", re.IGNORECASE)

def check_my_vulnerability(diff: FileDiff) -> list[SecurityHit]:
    hits = []
    for lineno, content in _added_lines(diff):
        if _MY_PATTERN.search(content):
            hits.append(SecurityHit(
                check=SecurityCheckType.MY_CHECK,
                file=diff.filename,
                line=lineno,
                snippet=content.strip()[:120],
                message="What the issue is.",
                fix="How to fix it.",
            ))
    return hits
```

---

## Reporting Bugs

Open an issue at https://github.com/the-ai-project-co/RunOwl/issues with:

- Steps to reproduce
- Expected behaviour
- Actual behaviour
- RunOwl version (`npx runowl --version`)
- OS and Python version

---

## Reporting Security Vulnerabilities

Please **do not** open a public issue for security vulnerabilities. Email security@runowl.ai instead. We aim to respond within 48 hours and will credit you in the changelog.

---

## Code of Conduct

Be kind, be constructive, assume good faith. We follow the [Contributor Covenant](https://www.contributor-covenant.org/).
