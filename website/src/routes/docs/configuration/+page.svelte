<script lang="ts">
	import DocsLayout from '$lib/components/docs/DocsLayout.svelte';
</script>

<DocsLayout
	title="Configuration"
	description="All RunOwl environment variables, tier detection, and configuration options."
>
<div class="prose">

<h1>Configuration</h1>
<p class="page-lead">
	RunOwl is configured entirely through environment variables. There is no config file — just set the vars in your shell, <code>.env</code> file, or CI secrets.
</p>

<h2>Environment Variables</h2>

<h3>Required</h3>

<table>
	<thead><tr><th>Variable</th><th>Description</th></tr></thead>
	<tbody>
		<tr>
			<td><code>GEMINI_API_KEY</code></td>
			<td>Google Gemini API key. Get one free at <a href="https://aistudio.google.com/" target="_blank">aistudio.google.com</a>.</td>
		</tr>
	</tbody>
</table>

<h3>Recommended</h3>

<table>
	<thead><tr><th>Variable</th><th>Description</th></tr></thead>
	<tbody>
		<tr>
			<td><code>GITHUB_TOKEN</code></td>
			<td>GitHub Personal Access Token or Actions token. Required for private repos, posting comments, and creating Check Runs. Needs <code>repo</code> scope.</td>
		</tr>
	</tbody>
</table>

<h3>Webhook Server</h3>

<table>
	<thead><tr><th>Variable</th><th>Default</th><th>Description</th></tr></thead>
	<tbody>
		<tr>
			<td><code>GITHUB_WEBHOOK_SECRET</code></td>
			<td>—</td>
			<td>HMAC-SHA256 secret for validating GitHub webhook payloads. Generate with <code>openssl rand -hex 32</code>. Strongly recommended.</td>
		</tr>
		<tr>
			<td><code>HOST</code></td>
			<td><code>0.0.0.0</code></td>
			<td>Server bind address.</td>
		</tr>
		<tr>
			<td><code>PORT</code></td>
			<td><code>8000</code></td>
			<td>Server port.</td>
		</tr>
		<tr>
			<td><code>ENV</code></td>
			<td><code>development</code></td>
			<td>Environment mode. Set to <code>production</code> in deployed environments.</td>
		</tr>
	</tbody>
</table>

<h3>GitHub App (Advanced)</h3>

<table>
	<thead><tr><th>Variable</th><th>Description</th></tr></thead>
	<tbody>
		<tr>
			<td><code>GITHUB_APP_ID</code></td>
			<td>GitHub App ID for organisation-wide installation.</td>
		</tr>
		<tr>
			<td><code>GITHUB_APP_PRIVATE_KEY_PATH</code></td>
			<td>Filesystem path to the GitHub App private key (<code>.pem</code> file).</td>
		</tr>
	</tbody>
</table>

<h3>Paid Tier</h3>

<table>
	<thead><tr><th>Variable</th><th>Description</th></tr></thead>
	<tbody>
		<tr>
			<td><code>RUNOWL_API_KEY</code></td>
			<td>Your RunOwl license key. Activates Team-tier features: deep security analysis, SOLID checks, and GitHub Check Runs.</td>
		</tr>
		<tr>
			<td><code>RUNOWL_TIER</code></td>
			<td>Explicit tier override: <code>free</code>, <code>team</code>, <code>business</code>, or <code>enterprise</code>. Takes precedence over API key detection. Useful for local development.</td>
		</tr>
	</tbody>
</table>

<h2>Tier Detection</h2>
<p>RunOwl automatically detects your subscription tier using this priority order:</p>

<ol class="step-list">
	<li>
		<div>
			<strong><code>RUNOWL_TIER</code> env var</strong> — if set, this always wins. Useful for forcing a specific tier locally: <code>RUNOWL_TIER=team npx runowl review ...</code>
		</div>
	</li>
	<li>
		<div>
			<strong><code>RUNOWL_API_KEY</code> present</strong> — any non-empty value activates Team tier features.
		</div>
	</li>
	<li>
		<div>
			<strong>Default</strong> — Free tier with surface security checks and basic code review.
		</div>
	</li>
</ol>

<h2>Feature Availability by Tier</h2>

<table>
	<thead>
		<tr>
			<th>Feature</th>
			<th>Free</th>
			<th>Team</th>
			<th>Business</th>
			<th>Enterprise</th>
		</tr>
	</thead>
	<tbody>
		<tr>
			<td>AI code review (P0–P3)</td>
			<td>✓</td><td>✓</td><td>✓</td><td>✓</td>
		</tr>
		<tr>
			<td>Surface security checks</td>
			<td>✓</td><td>✓</td><td>✓</td><td>✓</td>
		</tr>
		<tr>
			<td>Interactive Q&amp;A (<code>ask</code>)</td>
			<td>✓</td><td>✓</td><td>✓</td><td>✓</td>
		</tr>
		<tr>
			<td>GitHub webhook integration</td>
			<td>✓</td><td>✓</td><td>✓</td><td>✓</td>
		</tr>
		<tr>
			<td>CLI (<code>npx runowl</code>)</td>
			<td>✓</td><td>✓</td><td>✓</td><td>✓</td>
		</tr>
		<tr>
			<td>Deep OWASP security</td>
			<td>—</td><td>✓</td><td>✓</td><td>✓</td>
		</tr>
		<tr>
			<td>SOLID / architecture analysis</td>
			<td>—</td><td>✓</td><td>✓</td><td>✓</td>
		</tr>
		<tr>
			<td>GitHub Check Runs</td>
			<td>—</td><td>✓</td><td>✓</td><td>✓</td>
		</tr>
		<tr>
			<td>Priority support</td>
			<td>—</td><td>—</td><td>✓</td><td>✓</td>
		</tr>
		<tr>
			<td>SSO / SAML</td>
			<td>—</td><td>—</td><td>✓</td><td>✓</td>
		</tr>
		<tr>
			<td>Self-hosted deployment</td>
			<td>—</td><td>—</td><td>—</td><td>✓</td>
		</tr>
		<tr>
			<td>Audit logging</td>
			<td>—</td><td>—</td><td>—</td><td>✓</td>
		</tr>
		<tr>
			<td>SCIM provisioning</td>
			<td>—</td><td>—</td><td>—</td><td>✓</td>
		</tr>
	</tbody>
</table>

<h2>Example .env Files</h2>

<h3>Individual / Open Source</h3>

<div class="code-block">
	<div class="code-block-header">.env</div>
	<pre><code>GEMINI_API_KEY=AIzaSy...
GITHUB_TOKEN=ghp_...</code></pre>
</div>

<h3>Team (with webhook)</h3>

<div class="code-block">
	<div class="code-block-header">.env</div>
	<pre><code>GEMINI_API_KEY=AIzaSy...
GITHUB_TOKEN=ghp_...
GITHUB_WEBHOOK_SECRET=a8f2c3d...
RUNOWL_API_KEY=ro_live_...
PORT=8000
ENV=production</code></pre>
</div>

<h3>GitHub Actions</h3>

<div class="code-block">
	<div class="code-block-header">.github/workflows/review.yml (env block)</div>
	<pre><code>env:
  GEMINI_API_KEY: $&#123;&#123; secrets.GEMINI_API_KEY &#125;&#125;
  GITHUB_TOKEN: $&#123;&#123; secrets.GITHUB_TOKEN &#125;&#125;
  RUNOWL_API_KEY: $&#123;&#123; secrets.RUNOWL_API_KEY &#125;&#125;</code></pre>
</div>

<h2>Checking Your Tier</h2>
<p>Query the license endpoint on a running server:</p>

<div class="code-block">
	<div class="code-block-header">terminal</div>
	<pre><code>curl http://localhost:8000/license/tier
<span style="color:var(--muted)"># → &#123;"tier": "team", "is_paid": true&#125;</span>

curl http://localhost:8000/license/capabilities
<span style="color:var(--muted)"># → &#123;"features": ["surface_security", "code_review", "deep_security", ...]&#125;</span></code></pre>
</div>

</div>
</DocsLayout>
