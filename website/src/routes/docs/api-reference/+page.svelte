<script lang="ts">
	import DocsLayout from '$lib/components/docs/DocsLayout.svelte';
</script>

<DocsLayout
	title="API Reference"
	description="HTTP API reference for the RunOwl webhook server."
>
<div class="prose">

<h1>API Reference</h1>
<p class="page-lead">
	RunOwl exposes a small HTTP API when running as a server. The webhook endpoint receives GitHub events; the utility endpoints are useful for monitoring and debugging.
</p>

<h2>Base URL</h2>

<div class="code-block">
	<div class="code-block-header"></div>
	<pre><code>http://localhost:8000   <span style="color:var(--muted)"># default local</span>
https://your-server.com <span style="color:var(--muted)"># production</span></code></pre>
</div>

<h2>Endpoints</h2>

<h3>GET /health</h3>
<p>Health check endpoint. Returns server status and version. Use for uptime monitoring.</p>

<h4>Response</h4>
<div class="code-block">
	<div class="code-block-header">200 OK</div>
	<pre><code>{`{
  "status": "ok",
  "version": "0.1.0"
}`}</code></pre>
</div>

<div class="code-block">
	<div class="code-block-header">example</div>
	<pre><code>curl http://localhost:8000/health</code></pre>
</div>

<h3>POST /webhook/github</h3>
<p>GitHub webhook receiver. Accepts <code>pull_request</code> events and queues reviews as background jobs.</p>

<h4>Headers</h4>
<table>
	<thead><tr><th>Header</th><th>Required</th><th>Description</th></tr></thead>
	<tbody>
		<tr>
			<td><code>X-GitHub-Event</code></td>
			<td>Yes (set by GitHub)</td>
			<td>Event type, e.g. <code>pull_request</code></td>
		</tr>
		<tr>
			<td><code>X-Hub-Signature-256</code></td>
			<td>If <code>GITHUB_WEBHOOK_SECRET</code> set</td>
			<td>HMAC-SHA256 signature of the payload</td>
		</tr>
		<tr>
			<td><code>Content-Type</code></td>
			<td>Yes</td>
			<td><code>application/json</code></td>
		</tr>
	</tbody>
</table>

<h4>Responses</h4>
<table>
	<thead><tr><th>Status</th><th>Meaning</th></tr></thead>
	<tbody>
		<tr><td><code>202 Accepted</code></td><td>Event received and review queued</td></tr>
		<tr><td><code>200 OK</code></td><td>Event received but ignored (e.g. non-review action)</td></tr>
		<tr><td><code>401 Unauthorized</code></td><td>Signature validation failed</td></tr>
		<tr><td><code>422 Unprocessable Entity</code></td><td>Malformed payload</td></tr>
	</tbody>
</table>

<div class="callout info">
	<span class="callout-icon">ℹ️</span>
	<p>The server always returns immediately. The review runs asynchronously in the background. Results are posted as PR comments and Check Run updates.</p>
</div>

<h3>GET /license/tier</h3>
<p>Returns the current subscription tier.</p>

<h4>Response</h4>
<div class="code-block">
	<div class="code-block-header">200 OK</div>
	<pre><code>{`{
  "tier": "free",      // "free" | "team" | "business" | "enterprise"
  "is_paid": false
}`}</code></pre>
</div>

<div class="code-block">
	<div class="code-block-header">example</div>
	<pre><code>curl http://localhost:8000/license/tier</code></pre>
</div>

<h3>GET /license/capabilities</h3>
<p>Returns the full list of features available at the current tier.</p>

<h4>Response</h4>
<div class="code-block">
	<div class="code-block-header">200 OK</div>
	<pre><code>{`{
  "tier": "team",
  "is_paid": true,
  "features": [
    "surface_security",
    "code_review",
    "qa_session",
    "webhook",
    "deep_security",
    "solid_analysis",
    "check_runs"
  ]
}`}</code></pre>
</div>

<h2>Review Result Schema</h2>
<p>When using <code>--output json</code> from the CLI, the result follows this schema:</p>

<div class="code-block">
	<div class="code-block-header">ReviewResult</div>
	<pre><code>{`{
  "success": true,              // false if error occurred
  "error": null,                // error message if success=false
  "summary": {
    "total": 3,                 // total finding count
    "blocking": 1,              // P0+P1 count
    "by_severity": {
      "P0": 1,
      "P1": 0,
      "P2": 2,
      "P3": 0
    }
  },
  "findings": [
    {
      "severity": "P0",         // P0 | P1 | P2 | P3
      "type": "security",       // security | bug | investigation | informational
      "title": "Hardcoded JWT secret",
      "description": "JWT_SECRET is committed to source...",
      "citation": {
        "file": "src/auth.py",
        "line_start": 47,
        "line_end": 47
      },
      "fix": "Use os.environ['JWT_SECRET']...",
      "blocks_merge": true       // true for P0 and P1
    }
  ]
}`}</code></pre>
</div>

<h2>Finding Types</h2>
<table>
	<thead><tr><th>Type</th><th>Description</th></tr></thead>
	<tbody>
		<tr><td><code>security</code></td><td>Security vulnerability or risk</td></tr>
		<tr><td><code>bug</code></td><td>Logical error, crash risk, incorrect behaviour</td></tr>
		<tr><td><code>investigation</code></td><td>Requires human investigation; RunOwl flagged a concern but cannot confirm</td></tr>
		<tr><td><code>informational</code></td><td>P3 advisory — style, naming, minor improvement</td></tr>
	</tbody>
</table>

<h2>Rate Limits</h2>
<p>RunOwl imposes no rate limits of its own on the HTTP API. Rate limiting comes from upstream services:</p>
<ul>
	<li><strong>Gemini API</strong> — limits depend on your Google Cloud project tier</li>
	<li><strong>GitHub API</strong> — 5,000 requests/hour with a token; 60/hour anonymous</li>
</ul>

<h2>OpenAPI / Swagger</h2>
<p>When <code>ENV=development</code>, the server exposes OpenAPI docs at:</p>

<div class="code-block">
	<div class="code-block-header"></div>
	<pre><code>http://localhost:8000/docs     <span style="color:var(--muted)"># Swagger UI</span>
http://localhost:8000/redoc    <span style="color:var(--muted)"># ReDoc</span>
http://localhost:8000/openapi.json  <span style="color:var(--muted)"># Raw schema</span></code></pre>
</div>

</div>
</DocsLayout>
