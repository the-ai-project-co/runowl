<script lang="ts">
	import DocsLayout from '$lib/components/docs/DocsLayout.svelte';
</script>

<DocsLayout
	title="How It Works"
	description="A deep dive into RunOwl's Recursive Reasoning Loop (RLM) — the engine behind every code review."
>
<div class="prose">

<h1>How It Works</h1>
<p class="page-lead">
	RunOwl uses a Recursive Reasoning Loop (RLM) — a multi-turn conversation with Gemini that reads the diff, fetches relevant context, refines its analysis, and repeats until confident. No fixed rules, no keyword matching — genuine reasoning.
</p>

<h2>The Recursive Reasoning Loop</h2>
<p>Most AI code review tools read the diff once and output whatever the model produces. RunOwl works differently. It runs a loop:</p>

<div class="code-block">
	<div class="code-block-header">the loop</div>
	<pre><code>Receive PR diff + metadata
  │
  ▼
┌─────────────────────────────────┐
│  Send to Gemini                 │
│  (diff + conversation history)  │
└──────────┬──────────────────────┘
           │
     ┌─────▼─────┐
     │ Tool call? │
     └─────┬──────┘
     Yes   │   No
     │     │    │
     ▼     │    ▼
  Execute  │  Final text output
  tool     │  (findings)
     │     │
     └─────┘
  Append result to history
  Continue loop (max 20 iterations)</code></pre>
</div>

<h3>Why a Loop?</h3>
<p>Real bugs often require context beyond the diff itself. Consider:</p>
<ul>
	<li>A new endpoint that calls <code>authenticate()</code> — is that function actually secure? You need to read it.</li>
	<li>A SQL query that uses <code>user_id</code> — where does that value come from? You need to trace it.</li>
	<li>A new dependency — is it pinned? Is it well-maintained? You need to check <code>package.json</code>.</li>
</ul>
<p>The loop allows RunOwl to <em>discover</em> context rather than being handed it all upfront. This is what separates findings that cite exact lines from generic "potential SQL injection" alerts.</p>

<h2>Step by Step</h2>

<ol class="step-list">
	<li>
		<div>
			<strong>Fetch PR metadata</strong><br />
			RunOwl calls the GitHub API to fetch the PR title, description, author, branch names, commit list, and the unified diff for every changed file.
		</div>
	</li>
	<li>
		<div>
			<strong>Build the initial prompt</strong><br />
			The diff is formatted into a prompt alongside the PR title, author, and description. Files too large for the context window are noted as available via <code>FETCH_FILE</code>.
		</div>
	</li>
	<li>
		<div>
			<strong>Send to Gemini</strong><br />
			The prompt is sent to <code>gemini-2.0-flash</code> with three tool declarations: <code>FETCH_FILE</code>, <code>LIST_DIR</code>, and <code>SEARCH_CODE</code>. The system prompt instructs the model to investigate thoroughly before producing findings.
		</div>
	</li>
	<li>
		<div>
			<strong>Execute tool calls</strong><br />
			If Gemini requests a tool, RunOwl executes it against the GitHub API. Results are appended to the conversation and the model is called again.
		</div>
	</li>
	<li>
		<div>
			<strong>Receive final output</strong><br />
			When Gemini produces a text response (no tool calls), the loop ends. The output is a structured list of findings with severity, citations, and fix suggestions.
		</div>
	</li>
	<li>
		<div>
			<strong>Post-process findings</strong><br />
			A rule-based reclassifier validates severities using keyword signals (e.g., any finding mentioning "SQL injection" cannot be below P1). Citations are validated against the actual diff hunks to prevent hallucinations.
		</div>
	</li>
</ol>

<h2>Tool Calls</h2>
<p>The model has access to three read-only tools — no write access, no shell, no network:</p>

<table>
	<thead><tr><th>Tool</th><th>Description</th><th>Example</th></tr></thead>
	<tbody>
		<tr>
			<td><code>FETCH_FILE</code></td>
			<td>Fetch the content of a file at the PR's head commit</td>
			<td><code>FETCH_FILE("src/auth.py")</code></td>
		</tr>
		<tr>
			<td><code>LIST_DIR</code></td>
			<td>List the contents of a directory</td>
			<td><code>LIST_DIR("src/utils/")</code></td>
		</tr>
		<tr>
			<td><code>SEARCH_CODE</code></td>
			<td>Search for code patterns across the repository</td>
			<td><code>SEARCH_CODE("authenticate")</code></td>
		</tr>
	</tbody>
</table>

<div class="callout info">
	<span class="callout-icon">ℹ️</span>
	<p>All tool calls are logged to <code>~/.runowl/traces/</code> as JSON. You can inspect exactly what the model looked at and why.</p>
</div>

<h2>Safety Limits</h2>
<p>The loop has hard limits to prevent runaway costs:</p>

<table>
	<thead><tr><th>Limit</th><th>Value</th><th>Purpose</th></tr></thead>
	<tbody>
		<tr><td>Max iterations</td><td>20</td><td>Total loop iterations (tool calls + text turns)</td></tr>
		<tr><td>Max LLM calls</td><td>15</td><td>Maximum calls to Gemini API per review</td></tr>
		<tr><td>Tool result cap</td><td>8,000 chars</td><td>Truncates large files to avoid context explosion</td></tr>
		<tr><td>Execution timeout</td><td>60 seconds</td><td>Per-tool call timeout</td></tr>
		<tr><td>Output cap</td><td>256 KB</td><td>Total output size per review</td></tr>
	</tbody>
</table>

<h2>Severity Classification</h2>
<p>Findings are classified into four severity levels:</p>

<table>
	<thead><tr><th>Level</th><th>Name</th><th>Definition</th><th>Blocks merge?</th></tr></thead>
	<tbody>
		<tr>
			<td><span class="sev-badge sev-p0">P0</span></td>
			<td>Critical</td>
			<td>Data loss, auth bypass, production outage, exposed secrets</td>
			<td>Yes</td>
		</tr>
		<tr>
			<td><span class="sev-badge sev-p1">P1</span></td>
			<td>High</td>
			<td>Significant bug, security vulnerability, data integrity risk</td>
			<td>Yes</td>
		</tr>
		<tr>
			<td><span class="sev-badge sev-p2">P2</span></td>
			<td>Medium</td>
			<td>Code quality, minor security, non-critical bugs</td>
			<td>No</td>
		</tr>
		<tr>
			<td><span class="sev-badge sev-p3">P3</span></td>
			<td>Low</td>
			<td>Style, naming, minor improvements, informational</td>
			<td>No</td>
		</tr>
	</tbody>
</table>

<h3>Reclassification Rules</h3>
<p>The model's severity classification is validated and potentially upgraded by a rule-based reclassifier. This prevents the LLM from under-classifying serious issues:</p>
<ul>
	<li>Any finding matching SQL injection, RCE, auth bypass, or path traversal signals → minimum <span class="sev-badge sev-p0">P0</span></li>
	<li>Any finding matching XSS, CSRF, race condition, weak JWT signals → minimum <span class="sev-badge sev-p1">P1</span></li>
	<li>Security-type findings → never downgraded below <span class="sev-badge sev-p2">P2</span></li>
	<li>P0/P1 findings without a fix suggestion → fix is added or severity is downgraded</li>
</ul>

<h2>Citation Validation</h2>
<p>Every finding must cite a specific file and line number. RunOwl validates these citations against the actual diff hunks — if a finding claims line 47 of <code>src/auth.py</code> but that line wasn't changed in the PR, the citation is flagged.</p>
<p>This prevents the most common failure mode of AI reviewers: hallucinating issues in lines the PR didn't touch.</p>

<h2>Execution Traces</h2>
<p>Every review generates a trace file at <code>~/.runowl/traces/owner__repo__pr42.json</code>:</p>

<div class="code-block">
	<div class="code-block-header">trace example</div>
	<pre><code>{`{
  "iterations": 8,
  "llm_calls": 5,
  "tool_calls": 3,
  "steps": [
    { "type": "reasoning", "iteration": 0, "content": "Iteration 1" },
    { "type": "llm_call",  "iteration": 0, "content": "Gemini response received" },
    { "type": "tool_call", "iteration": 0, "content": "FETCH_FILE({'path': 'src/auth.py'})",
      "metadata": { "tool": "FETCH_FILE", "args": { "path": "src/auth.py" } } },
    { "type": "tool_call", "iteration": 1, "content": "SEARCH_CODE({'query': 'JWT_SECRET'})" },
    { "type": "output",    "iteration": 4, "content": "[P0] security: Hardcoded JWT secret..." }
  ]
}`}</code></pre>
</div>

<h2>Model</h2>
<p>RunOwl uses <code>gemini-2.0-flash</code> by default — a fast, capable model well-suited for code analysis. You can override this with <code>--model</code>:</p>

<div class="code-block">
	<div class="code-block-header">terminal</div>
	<pre><code><span style="color:var(--muted)"># Use a more powerful model for complex PRs</span>
npx runowl review --url ... --model gemini-2.0-pro</code></pre>
</div>

</div>
</DocsLayout>
