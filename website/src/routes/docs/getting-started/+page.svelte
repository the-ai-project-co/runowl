<script lang="ts">
	import DocsLayout from '$lib/components/docs/DocsLayout.svelte';
</script>

<DocsLayout
	title="Getting Started"
	description="Install RunOwl and run your first AI code review in under 2 minutes."
>
<div class="prose">

<h1>Getting Started</h1>
<p class="page-lead">
	Run your first AI-powered code review in under two minutes — no sign-up required.
</p>

<h2>Prerequisites</h2>
<p>You need two things before you start:</p>
<ul>
	<li><strong>Node.js 18+</strong> — for the <code>npx runowl</code> CLI</li>
	<li><strong>A Gemini API key</strong> — free from <a href="https://aistudio.google.com/" target="_blank">aistudio.google.com</a></li>
</ul>

<div class="callout tip">
	<span class="callout-icon">💡</span>
	<p>A GitHub token is optional for public repos, but strongly recommended. Without it you'll hit GitHub's anonymous rate limit (60 req/hr) on large PRs.</p>
</div>

<h2>Quick Start</h2>
<p>Set your API key, then point RunOwl at any GitHub PR:</p>

<div class="code-block">
	<div class="code-block-header">terminal</div>
	<pre><code><span style="color:var(--muted)"># 1. Set your Gemini API key</span>
export GEMINI_API_KEY=your-key-here

<span style="color:var(--muted)"># 2. Run a review (no install needed)</span>
npx runowl review --url https://github.com/owner/repo/pull/42</code></pre>
</div>

<p>That's it. RunOwl will fetch the PR, run its Recursive Reasoning Loop, and print a structured review with severity-tagged findings.</p>

<h2>Installation</h2>
<p>For repeated use, install globally to avoid the <code>npx</code> download each time:</p>

<div class="code-block">
	<div class="code-block-header">terminal</div>
	<pre><code>npm install -g runowl

<span style="color:var(--muted)"># Or with pnpm / bun</span>
pnpm add -g runowl
bun add -g runowl</code></pre>
</div>

<h2>Environment Setup</h2>
<p>Create a <code>.env</code> file in your project or home directory:</p>

<div class="code-block">
	<div class="code-block-header">.env</div>
	<pre><code><span style="color:var(--muted)"># Required</span>
GEMINI_API_KEY=AIza...

<span style="color:var(--muted)"># Recommended (needed for private repos)</span>
GITHUB_TOKEN=ghp_...

<span style="color:var(--muted)"># Paid features (Team tier)</span>
RUNOWL_API_KEY=ro_live_...</code></pre>
</div>

<div class="callout info">
	<span class="callout-icon">ℹ️</span>
	<p>RunOwl loads <code>.env</code> files automatically from the working directory. You can also export variables directly in your shell or CI environment.</p>
</div>

<h2>Your First Review</h2>
<ol class="step-list">
	<li>
		<div>
			<strong>Get a Gemini API key</strong><br />
			Visit <a href="https://aistudio.google.com/app/apikey" target="_blank">aistudio.google.com</a>, sign in with Google, and create a free API key. The free quota is more than enough for dozens of reviews per day.
		</div>
	</li>
	<li>
		<div>
			<strong>Set the environment variable</strong><br />
			<code>export GEMINI_API_KEY=your-key-here</code> in your shell, or add it to a <code>.env</code> file.
		</div>
	</li>
	<li>
		<div>
			<strong>Run a review</strong><br />
			<code>npx runowl review --url https://github.com/owner/repo/pull/42</code>
		</div>
	</li>
	<li>
		<div>
			<strong>Read the output</strong><br />
			Findings are sorted by severity: <span class="sev-badge sev-p0">P0</span> critical first, down to <span class="sev-badge sev-p3">P3</span> low. Each finding includes the file, line number, and a fix suggestion.
		</div>
	</li>
</ol>

<h2>Sample Output</h2>

<div class="code-block">
	<div class="code-block-header">terminal output</div>
	<pre><code>✓ Fetching PR #42 — "Add user authentication"
✓ Reasoning loop: 12 iterations · 8 tool calls

──────────────────────────────────────────
  RunOwl Code Review · PR #42
──────────────────────────────────────────

[P0] SECURITY  Hardcoded JWT secret
  src/auth.py:47
  JWT_SECRET = "my-app-secret-key" is committed to source.
  Fix: Use os.environ["JWT_SECRET"] and rotate the key immediately.

[P1] BUG  Missing auth on admin endpoint
  src/routes.py:103
  The /admin/users route has no authentication decorator.
  Fix: Add @require_auth decorator before the route handler.

[P2] BUG  SQL query uses string concatenation
  src/db.py:29
  f"SELECT * FROM users WHERE id = &#123;user_id&#125;" is vulnerable to injection.
  Fix: Use parameterised queries: cursor.execute("... WHERE id = ?", (user_id,))

──────────────────────────────────────────
  3 findings  ·  1 blocking  ·  check run: FAILED
──────────────────────────────────────────</code></pre>
</div>

<h2>Next Steps</h2>
<ul>
	<li><a href="/docs/cli-reference">CLI Reference</a> — all flags and output formats</li>
	<li><a href="/docs/github-integration">GitHub Integration</a> — automatic PR reviews via webhook</li>
	<li><a href="/docs/configuration">Configuration</a> — full environment variable reference</li>
</ul>

</div>
</DocsLayout>
