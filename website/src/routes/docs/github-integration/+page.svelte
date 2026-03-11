<script lang="ts">
	import DocsLayout from '$lib/components/docs/DocsLayout.svelte';
</script>

<DocsLayout
	title="GitHub Integration"
	description="Set up automatic PR reviews via GitHub webhooks and GitHub Check Runs."
>
<div class="prose">

<h1>GitHub Integration</h1>
<p class="page-lead">
	RunOwl integrates with GitHub in two ways: automatic reviews via webhooks, and status feedback via Check Runs. Set it up once and every PR gets reviewed automatically.
</p>

<h2>Webhook Setup</h2>
<p>The webhook server listens for <code>pull_request</code> events and triggers a review whenever a PR is opened, updated, or reopened.</p>

<h3>1. Start the Server</h3>

<div class="code-block">
	<div class="code-block-header">terminal</div>
	<pre><code><span style="color:var(--muted)"># With uv (recommended)</span>
uv run uvicorn main:app --host 0.0.0.0 --port 8000

<span style="color:var(--muted)"># Or with pip</span>
pip install runowl-server
uvicorn main:app --host 0.0.0.0 --port 8000</code></pre>
</div>

<h3>2. Configure the Webhook in GitHub</h3>
<ol class="step-list">
	<li>
		<div>Go to your repository → <strong>Settings → Webhooks → Add webhook</strong></div>
	</li>
	<li>
		<div>
			Set <strong>Payload URL</strong> to your server: <code>https://your-server.com/webhook/github</code>
		</div>
	</li>
	<li>
		<div>Set <strong>Content type</strong> to <code>application/json</code></div>
	</li>
	<li>
		<div>
			Generate a secret: <code>openssl rand -hex 32</code> — copy it as <strong>Secret</strong>, and set it as <code>GITHUB_WEBHOOK_SECRET</code> in your environment
		</div>
	</li>
	<li>
		<div>Under <strong>Which events?</strong>, select <strong>Let me select individual events</strong> → check <strong>Pull requests</strong></div>
	</li>
	<li>
		<div>Click <strong>Add webhook</strong></div>
	</li>
</ol>

<div class="callout warning">
	<span class="callout-icon">⚠️</span>
	<p><strong>Always set a webhook secret.</strong> Without it, anyone can send fake events to your server. RunOwl verifies the <code>X-Hub-Signature-256</code> header when <code>GITHUB_WEBHOOK_SECRET</code> is set.</p>
</div>

<h3>3. Environment Variables</h3>

<div class="code-block">
	<div class="code-block-header">.env</div>
	<pre><code>GEMINI_API_KEY=AIza...
GITHUB_TOKEN=ghp_...
GITHUB_WEBHOOK_SECRET=your-secret-here</code></pre>
</div>

<h3>Webhook Payload</h3>
<p>RunOwl processes these <code>pull_request</code> event actions:</p>
<ul>
	<li><code>opened</code> — new PR created</li>
	<li><code>synchronize</code> — new commits pushed to the branch</li>
	<li><code>reopened</code> — closed PR was reopened</li>
</ul>
<p>All other actions (assigned, labeled, closed, etc.) are silently ignored. The server responds <code>202 Accepted</code> immediately and runs the review as a background job.</p>

<h2>GitHub Check Runs <span class="pill pill-paid">Team</span></h2>
<p>With a Team subscription, RunOwl creates a GitHub Check Run on every PR — giving you a pass/fail status directly in the PR interface.</p>

<h3>How It Works</h3>
<ol class="step-list">
	<li>
		<div>When a PR opens, RunOwl immediately creates a check run with status <strong>in_progress</strong>. The PR shows "RunOwl Code Review — checking..." in the Checks section.</div>
	</li>
	<li>
		<div>The review runs in the background (typically 30–90 seconds depending on PR size).</div>
	</li>
	<li>
		<div>
			When complete, the check run is updated:
			<ul>
				<li><strong>success</strong> — no P0 or P1 findings</li>
				<li><strong>failure</strong> — one or more P0/P1 findings found</li>
			</ul>
		</div>
	</li>
	<li>
		<div>If branch protection rules require the RunOwl check to pass, P0/P1 findings <strong>block the merge button</strong>.</div>
	</li>
</ol>

<h3>Setting Up Branch Protection</h3>
<ol class="step-list">
	<li><div>Go to <strong>Settings → Branches → Add rule</strong> for your main branch</div></li>
	<li><div>Enable <strong>Require status checks to pass before merging</strong></div></li>
	<li><div>Search for and add <strong>RunOwl Code Review</strong> to required checks</div></li>
	<li><div>Save the rule</div></li>
</ol>

<h2>PR Comments</h2>
<p>RunOwl posts its findings as a PR comment in structured markdown format:</p>

<div class="code-block">
	<div class="code-block-header">example PR comment</div>
	<pre><code>## RunOwl Code Review

### 🔴 P0 CRITICAL · Security

**Hardcoded JWT secret**
**Location:** `src/auth.py:47`

`JWT_SECRET = "my-app-secret-key"` is committed to source.
Rotate the key immediately — it is now compromised.

**Fix:** Use `os.environ["JWT_SECRET"]` and store the secret in your
secrets manager (GitHub Actions secrets, Vault, etc.)

---
### 🟡 P1 HIGH · Bug

**Missing authentication on /admin endpoint**
**Location:** `src/routes.py:103`

...

---
*3 findings · 1 blocking · [View full trace](https://runowl.ai)*</code></pre>
</div>

<h2>GitHub Token Permissions</h2>
<p>The <code>GITHUB_TOKEN</code> needs these scopes depending on what you're doing:</p>

<table>
	<thead><tr><th>Feature</th><th>Required Scope</th></tr></thead>
	<tbody>
		<tr><td>Reading public PRs</td><td><em>None (anonymous)</em></td></tr>
		<tr><td>Reading private PRs</td><td><code>repo</code></td></tr>
		<tr><td>Posting PR comments</td><td><code>repo</code></td></tr>
		<tr><td>Creating Check Runs</td><td><code>repo</code> or <code>checks:write</code></td></tr>
		<tr><td>Organization repos</td><td><code>read:org</code></td></tr>
	</tbody>
</table>

<div class="callout tip">
	<span class="callout-icon">💡</span>
	<p>For GitHub Actions workflows, use the automatically-provided <code>secrets.GITHUB_TOKEN</code>. It has all required permissions by default. No need to create a PAT.</p>
</div>

<h2>GitHub App (Advanced)</h2>
<p>For organisation-wide deployment, you can install RunOwl as a GitHub App instead of using a PAT. This provides better security, clearer audit trails, and per-repo installation control.</p>

<div class="code-block">
	<div class="code-block-header">.env</div>
	<pre><code><span style="color:var(--muted)"># GitHub App credentials</span>
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=/etc/runowl/private-key.pem

<span style="color:var(--muted)"># Webhook secret (same as above)</span>
GITHUB_WEBHOOK_SECRET=your-secret-here</code></pre>
</div>

<h2>Rate Limits</h2>
<p>RunOwl is designed to stay well within GitHub's rate limits:</p>
<ul>
	<li><strong>LRU caching</strong> — file content is cached (200 entries) to avoid re-fetching the same files across tool calls</li>
	<li><strong>Concurrency limit</strong> — max 5 concurrent GitHub API requests</li>
	<li><strong>Exponential backoff</strong> — automatic retries on 429 and 5xx responses (via tenacity)</li>
	<li><strong>Authenticated requests</strong> — 5,000 req/hr (vs 60/hr anonymous)</li>
</ul>

</div>
</DocsLayout>
