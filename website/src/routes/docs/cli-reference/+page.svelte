<script lang="ts">
	import DocsLayout from '$lib/components/docs/DocsLayout.svelte';
</script>

<DocsLayout
	title="CLI Reference"
	description="Complete reference for all RunOwl CLI commands, flags, and output formats."
>
<div class="prose">

<h1>CLI Reference</h1>
<p class="page-lead">
	RunOwl exposes two commands: <code>review</code> and <code>ask</code>. Both accept a GitHub PR URL and produce structured output.
</p>

<h2>review</h2>
<p>Runs a full AI code review on a pull request.</p>

<div class="code-block">
	<div class="code-block-header">usage</div>
	<pre><code>npx runowl review --url &lt;github-pr-url&gt; [options]</code></pre>
</div>

<h3>Options</h3>

<table>
	<thead>
		<tr>
			<th>Flag</th>
			<th>Short</th>
			<th>Default</th>
			<th>Description</th>
		</tr>
	</thead>
	<tbody>
		<tr>
			<td><code>--url</code></td>
			<td><code>-u</code></td>
			<td><em>required</em></td>
			<td>GitHub PR URL, e.g. <code>https://github.com/owner/repo/pull/42</code></td>
		</tr>
		<tr>
			<td><code>--output</code></td>
			<td><code>-o</code></td>
			<td><code>text</code></td>
			<td>Output format: <code>text</code>, <code>markdown</code>, or <code>json</code></td>
		</tr>
		<tr>
			<td><code>--submit</code></td>
			<td></td>
			<td><code>false</code></td>
			<td>Post review as a PR comment (requires <code>GITHUB_TOKEN</code>)</td>
		</tr>
		<tr>
			<td><code>--expert</code></td>
			<td></td>
			<td><code>false</code></td>
			<td>Enable deep OWASP + SOLID analysis (requires Team tier)</td>
		</tr>
		<tr>
			<td><code>--question</code></td>
			<td><code>-q</code></td>
			<td></td>
			<td>Ask a specific question alongside the review</td>
		</tr>
		<tr>
			<td><code>--quiet</code></td>
			<td></td>
			<td><code>false</code></td>
			<td>Suppress progress spinners and status output</td>
		</tr>
		<tr>
			<td><code>--model</code></td>
			<td><code>-m</code></td>
			<td><code>gemini-2.0-flash</code></td>
			<td>Gemini model ID to use</td>
		</tr>
	</tbody>
</table>

<h3>Examples</h3>

<div class="code-block">
	<div class="code-block-header">basic review</div>
	<pre><code>npx runowl review --url https://github.com/owner/repo/pull/42</code></pre>
</div>

<div class="code-block">
	<div class="code-block-header">json output for CI pipelines</div>
	<pre><code>npx runowl review \
  --url https://github.com/owner/repo/pull/42 \
  --output json \
  --quiet</code></pre>
</div>

<div class="code-block">
	<div class="code-block-header">post review as PR comment</div>
	<pre><code>GITHUB_TOKEN=ghp_... npx runowl review \
  --url https://github.com/owner/repo/pull/42 \
  --submit</code></pre>
</div>

<div class="code-block">
	<div class="code-block-header">deep analysis (paid)</div>
	<pre><code>RUNOWL_API_KEY=ro_live_... npx runowl review \
  --url https://github.com/owner/repo/pull/42 \
  --expert</code></pre>
</div>

<div class="code-block">
	<div class="code-block-header">focused question</div>
	<pre><code>npx runowl review \
  --url https://github.com/owner/repo/pull/42 \
  --question "Are there any SQL injection risks in the new endpoints?"</code></pre>
</div>

<h2>ask</h2>
<p>Starts an interactive Q&amp;A session about a pull request. Maintains conversation history so follow-up questions have full context.</p>

<div class="code-block">
	<div class="code-block-header">usage</div>
	<pre><code>npx runowl ask --url &lt;github-pr-url&gt; [options]</code></pre>
</div>

<h3>Options</h3>

<table>
	<thead>
		<tr>
			<th>Flag</th>
			<th>Short</th>
			<th>Default</th>
			<th>Description</th>
		</tr>
	</thead>
	<tbody>
		<tr>
			<td><code>--url</code></td>
			<td><code>-u</code></td>
			<td><em>required</em></td>
			<td>GitHub PR URL</td>
		</tr>
		<tr>
			<td><code>--question</code></td>
			<td><code>-q</code></td>
			<td></td>
			<td>Ask a single question non-interactively and exit</td>
		</tr>
		<tr>
			<td><code>--quiet</code></td>
			<td></td>
			<td><code>false</code></td>
			<td>Suppress status output</td>
		</tr>
		<tr>
			<td><code>--model</code></td>
			<td><code>-m</code></td>
			<td><code>gemini-2.0-flash</code></td>
			<td>Gemini model ID to use</td>
		</tr>
	</tbody>
</table>

<h3>Examples</h3>

<div class="code-block">
	<div class="code-block-header">interactive session</div>
	<pre><code>npx runowl ask --url https://github.com/owner/repo/pull/42

<span style="color:var(--muted)">You &gt; Are there race conditions in the worker pool changes?
RunOwl &gt; Yes — there's a TOCTOU issue in claim_job() at src/workers/pool.py:83...

You &gt; How would you fix it?
RunOwl &gt; Use UPDATE ... WHERE status = 'pending' RETURNING id — a single atomic operation.

You &gt; quit</span></code></pre>
</div>

<div class="code-block">
	<div class="code-block-header">single question (non-interactive)</div>
	<pre><code>npx runowl ask \
  --url https://github.com/owner/repo/pull/42 \
  --question "What changed in the database layer?"</code></pre>
</div>

<h3>Built-in Commands</h3>
<p>During an interactive session, these commands are available:</p>

<table>
	<thead><tr><th>Command</th><th>Description</th></tr></thead>
	<tbody>
		<tr><td><code>quit</code> / <code>exit</code> / <code>q</code></td><td>End the session</td></tr>
		<tr><td><code>reset</code></td><td>Clear conversation history and start fresh</td></tr>
		<tr><td><code>history</code></td><td>Show all previous questions and answers</td></tr>
		<tr><td><code>files</code></td><td>List all files changed in the PR</td></tr>
		<tr><td><code>info</code></td><td>Show PR metadata (title, author, branch, stats)</td></tr>
		<tr><td><code>help</code></td><td>Show available commands</td></tr>
	</tbody>
</table>

<h2>Output Formats</h2>

<h3>text (default)</h3>
<p>Colourised terminal output using Rich. Best for interactive use.</p>

<h3>markdown</h3>
<p>GitHub-flavoured markdown. Suitable for piping into files or pasting into GitHub comments manually.</p>

<div class="code-block">
	<div class="code-block-header">save markdown review</div>
	<pre><code>npx runowl review --url ... --output markdown > review.md</code></pre>
</div>

<h3>json</h3>
<p>Machine-readable JSON. Designed for CI/CD pipelines and downstream tooling.</p>

<div class="code-block">
	<div class="code-block-header">json schema</div>
	<pre><code>{`{
  "success": true,
  "summary": {
    "total": 3,
    "blocking": 1,
    "by_severity": { "P0": 1, "P1": 0, "P2": 2, "P3": 0 }
  },
  "findings": [
    {
      "severity": "P0",
      "type": "security",
      "title": "Hardcoded JWT secret",
      "description": "JWT_SECRET is committed to source...",
      "citation": { "file": "src/auth.py", "line_start": 47, "line_end": 47 },
      "fix": "Use os.environ['JWT_SECRET'] and rotate immediately.",
      "blocks_merge": true
    }
  ]
}`}</code></pre>
</div>

<h2>Exit Codes</h2>

<table>
	<thead><tr><th>Code</th><th>Meaning</th></tr></thead>
	<tbody>
		<tr><td><code>0</code></td><td>Review completed, no blocking findings (P0/P1)</td></tr>
		<tr><td><code>1</code></td><td>Review completed with blocking findings, or an error occurred</td></tr>
	</tbody>
</table>

<div class="callout tip">
	<span class="callout-icon">💡</span>
	<p>Use the exit code in CI to fail a pipeline when blocking issues are found: <code>npx runowl review --url "$PR_URL" --quiet && echo "Review passed"</code></p>
</div>

<h2>CI/CD Integration</h2>

<div class="code-block">
	<div class="code-block-header">.github/workflows/runowl.yml</div>
	<pre><code>name: RunOwl Code Review

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run RunOwl
        env:
          GEMINI_API_KEY: $&#123;&#123; secrets.GEMINI_API_KEY &#125;&#125;
          GITHUB_TOKEN: $&#123;&#123; secrets.GITHUB_TOKEN &#125;&#125;
        run: |
          npx runowl review \
            --url "$&#123;&#123; github.event.pull_request.html_url &#125;&#125;" \
            --output json \
            --quiet</code></pre>
</div>

</div>
</DocsLayout>
