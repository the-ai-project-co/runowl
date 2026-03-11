<script lang="ts">
	import DocsLayout from '$lib/components/docs/DocsLayout.svelte';
</script>

<DocsLayout
	title="Security Analysis"
	description="RunOwl's two-tier security analysis: surface checks (free) and deep OWASP analysis (paid)."
>
<div class="prose">

<h1>Security Analysis</h1>
<p class="page-lead">
	RunOwl performs security analysis in two tiers: fast pattern-based surface checks available to everyone, and deep OWASP-aligned analysis for paid subscribers.
</p>

<h2>Surface Checks <span class="pill pill-free">Free</span></h2>
<p>Pattern-matching rules applied to every added line in the diff. Fast, deterministic, and zero false-negative on known patterns.</p>

<table>
	<thead><tr><th>Check</th><th>What it detects</th><th>Example</th></tr></thead>
	<tbody>
		<tr>
			<td>Hardcoded secrets</td>
			<td>Passwords, API keys, tokens committed directly in source</td>
			<td><code>api_key = "sk-abc123"</code></td>
		</tr>
		<tr>
			<td>SQL injection</td>
			<td>String concatenation or f-strings used to build SQL queries</td>
			<td><code>f"SELECT * FROM users WHERE id = &#123;id&#125;"</code></td>
		</tr>
		<tr>
			<td>XSS risks</td>
			<td>Unescaped user input inserted into HTML via DOM manipulation</td>
			<td><code>element.innerHTML = userInput</code></td>
		</tr>
		<tr>
			<td>Missing authentication</td>
			<td>Route handlers or admin endpoints without auth decorators or middleware</td>
			<td><code>@app.route("/admin/users")</code> with no guard</td>
		</tr>
		<tr>
			<td>Hardcoded credentials</td>
			<td>Username/password pairs in source</td>
			<td><code>ADMIN_PASSWORD = "hunter2"</code></td>
		</tr>
		<tr>
			<td>Unpinned dependencies</td>
			<td>Package files using <code>latest</code> or <code>*</code> versions</td>
			<td><code>"express": "latest"</code></td>
		</tr>
	</tbody>
</table>

<div class="callout info">
	<span class="callout-icon">ℹ️</span>
	<p>Surface checks run against <strong>added lines only</strong>. Unchanged code is not scanned — only what your PR actually introduced.</p>
</div>

<h2>Deep Security Analysis <span class="pill pill-paid">Team</span></h2>
<p>Enable with <code>--expert</code> flag. Performs OWASP Top 10-aligned analysis through the Reasoning Loop — the model investigates code paths, not just patterns.</p>

<h3>OWASP Top 10 Coverage</h3>

<table>
	<thead><tr><th>OWASP Category</th><th>What RunOwl checks</th></tr></thead>
	<tbody>
		<tr>
			<td>A01 Broken Access Control</td>
			<td>Missing auth, privilege escalation, IDOR, path traversal</td>
		</tr>
		<tr>
			<td>A02 Cryptographic Failures</td>
			<td>MD5/SHA1 for passwords, hardcoded keys, weak cipher modes (ECB), improper IV usage</td>
		</tr>
		<tr>
			<td>A03 Injection</td>
			<td>SQL, NoSQL, LDAP, OS command, expression language injection</td>
		</tr>
		<tr>
			<td>A04 Insecure Design</td>
			<td>Missing rate limiting, insecure default configurations</td>
		</tr>
		<tr>
			<td>A05 Security Misconfiguration</td>
			<td>CORS wildcards, debug endpoints in production, permissive CSP</td>
		</tr>
		<tr>
			<td>A06 Vulnerable Components</td>
			<td>Known vulnerable versions, unpinned dependencies, supply chain risks</td>
		</tr>
		<tr>
			<td>A07 Auth & Session Failures</td>
			<td>Weak JWT (none algorithm, HS256 with exposed secret), session fixation, improper logout</td>
		</tr>
		<tr>
			<td>A08 Software Integrity Failures</td>
			<td>Missing integrity checks on third-party scripts, CI/CD configuration risks</td>
		</tr>
		<tr>
			<td>A09 Logging Failures</td>
			<td>Missing security event logging, logging sensitive data</td>
		</tr>
		<tr>
			<td>A10 SSRF</td>
			<td>Unvalidated URLs passed to HTTP clients, internal metadata endpoints</td>
		</tr>
	</tbody>
</table>

<h3>Additional Deep Checks</h3>

<table>
	<thead><tr><th>Category</th><th>Checks</th></tr></thead>
	<tbody>
		<tr>
			<td>Race conditions</td>
			<td>TOCTOU vulnerabilities, non-atomic check-then-act, concurrent resource access without locks</td>
		</tr>
		<tr>
			<td>Deserialization</td>
			<td>Unsafe pickle/eval/exec usage, deserializing untrusted data</td>
		</tr>
		<tr>
			<td>JWT security</td>
			<td>Algorithm confusion attacks, signature validation bypass, missing expiry</td>
		</tr>
		<tr>
			<td>Supply chain</td>
			<td>Suspicious new dependencies, typosquatting patterns, missing lockfiles</td>
		</tr>
	</tbody>
</table>

<h2>Severity Mapping</h2>
<p>Security findings follow a strict severity floor — the reclassifier ensures these are never downgraded:</p>

<table>
	<thead><tr><th>Finding Type</th><th>Minimum Severity</th></tr></thead>
	<tbody>
		<tr><td>SQL injection, RCE, auth bypass, path traversal, XXE, SSRF</td><td><span class="sev-badge sev-p0">P0</span></td></tr>
		<tr><td>XSS, CSRF, open redirect, weak JWT, race condition (TOCTOU)</td><td><span class="sev-badge sev-p1">P1</span></td></tr>
		<tr><td>CORS misconfiguration, missing security headers, weak cipher</td><td><span class="sev-badge sev-p2">P2</span></td></tr>
		<tr><td>Unpinned deps, informational security notes</td><td><span class="sev-badge sev-p3">P3</span></td></tr>
	</tbody>
</table>

<div class="callout danger">
	<span class="callout-icon">🔴</span>
	<p><strong>P0 and P1 findings block the merge</strong> when GitHub Check Runs are configured. Your team cannot merge a PR with an exposed secret or an auth bypass — period.</p>
</div>

<h2>Architecture Analysis <span class="pill pill-paid">Team</span></h2>
<p>Alongside deep security, <code>--expert</code> also enables SOLID principle analysis and code smell detection.</p>

<h3>SOLID Checks</h3>

<table>
	<thead><tr><th>Principle</th><th>What's checked</th></tr></thead>
	<tbody>
		<tr><td>Single Responsibility</td><td>Classes doing too many things; methods with multiple distinct concerns</td></tr>
		<tr><td>Open/Closed</td><td>Code that requires modification to extend; missing abstraction points</td></tr>
		<tr><td>Liskov Substitution</td><td>Subclass overrides that break parent class contracts</td></tr>
		<tr><td>Interface Segregation</td><td>Fat interfaces forcing implementations to stub unused methods</td></tr>
		<tr><td>Dependency Inversion</td><td>High-level modules depending on concrete implementations</td></tr>
	</tbody>
</table>

<h3>Code Smells</h3>
<ul>
	<li><strong>God objects</strong> — classes with too many responsibilities and dependencies</li>
	<li><strong>Deep nesting</strong> — excessive if/for/try nesting (typically &gt;4 levels)</li>
	<li><strong>Long methods</strong> — functions doing too much; hard to test in isolation</li>
	<li><strong>Feature envy</strong> — methods that use another class's data more than their own</li>
	<li><strong>Primitive obsession</strong> — over-use of primitives where value objects belong</li>
</ul>

<h3>Supported Languages</h3>
<p>Architecture analysis runs on: Python, TypeScript, JavaScript, Java, Go, C#, Ruby.</p>

<h2>Enabling Expert Mode</h2>

<div class="code-block">
	<div class="code-block-header">terminal</div>
	<pre><code>RUNOWL_API_KEY=ro_live_... npx runowl review \
  --url https://github.com/owner/repo/pull/42 \
  --expert</code></pre>
</div>

<p>Without a valid API key, <code>--expert</code> will note that deep analysis requires a Team subscription and fall back to surface checks only.</p>

</div>
</DocsLayout>
