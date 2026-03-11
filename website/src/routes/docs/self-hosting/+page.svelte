<script lang="ts">
	import DocsLayout from '$lib/components/docs/DocsLayout.svelte';
</script>

<DocsLayout
	title="Self-Hosting"
	description="Run the RunOwl webhook server on your own infrastructure."
>
<div class="prose">

<h1>Self-Hosting</h1>
<p class="page-lead">
	Run the full RunOwl stack on your own infrastructure. Self-hosting gives you complete control over data, networking, and deployment.
</p>

<h2>Requirements</h2>
<ul>
	<li>Python 3.12+</li>
	<li><code>uv</code> package manager (recommended) or <code>pip</code></li>
	<li>A server reachable from GitHub's IP ranges (for webhooks)</li>
	<li>A valid <code>GEMINI_API_KEY</code></li>
</ul>

<h2>Installation</h2>

<div class="code-block">
	<div class="code-block-header">terminal</div>
	<pre><code><span style="color:var(--muted)"># Clone the repo</span>
git clone https://github.com/the-ai-project-co/RunOwl.git
cd RunOwl

<span style="color:var(--muted)"># Install dependencies with uv</span>
uv sync

<span style="color:var(--muted)"># Or with pip</span>
pip install -e .</code></pre>
</div>

<h2>Environment Setup</h2>

<div class="code-block">
	<div class="code-block-header">terminal</div>
	<pre><code><span style="color:var(--muted)"># Copy the example env file</span>
cp .env.example .env

<span style="color:var(--muted)"># Edit with your values</span>
nano .env</code></pre>
</div>

<div class="code-block">
	<div class="code-block-header">.env</div>
	<pre><code>GEMINI_API_KEY=AIzaSy...
GITHUB_TOKEN=ghp_...
GITHUB_WEBHOOK_SECRET=your-secret-here
PORT=8000
ENV=production</code></pre>
</div>

<h2>Running the Server</h2>

<div class="code-block">
	<div class="code-block-header">terminal</div>
	<pre><code><span style="color:var(--muted)"># With uv</span>
uv run uvicorn main:app --host 0.0.0.0 --port 8000

<span style="color:var(--muted)"># With pip / uvicorn directly</span>
uvicorn main:app --host 0.0.0.0 --port 8000

<span style="color:var(--muted)"># Verify it's running</span>
curl http://localhost:8000/health
<span style="color:var(--green)"># → &#123;"status": "ok", "version": "0.1.0"&#125;</span></code></pre>
</div>

<h2>Production Deployment</h2>

<h3>systemd Service</h3>

<div class="code-block">
	<div class="code-block-header">/etc/systemd/system/runowl.service</div>
	<pre><code>[Unit]
Description=RunOwl webhook server
After=network.target

[Service]
Type=simple
User=runowl
WorkingDirectory=/opt/runowl
EnvironmentFile=/opt/runowl/.env
ExecStart=uv run uvicorn main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target</code></pre>
</div>

<div class="code-block">
	<div class="code-block-header">terminal</div>
	<pre><code>sudo systemctl enable runowl
sudo systemctl start runowl
sudo systemctl status runowl</code></pre>
</div>

<h3>Docker</h3>

<div class="code-block">
	<div class="code-block-header">Dockerfile</div>
	<pre><code>FROM python:3.12-slim

WORKDIR /app
COPY . .

RUN pip install uv && uv sync --no-dev

ENV HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]</code></pre>
</div>

<div class="code-block">
	<div class="code-block-header">terminal</div>
	<pre><code>docker build -t runowl .
docker run -d \
  --env-file .env \
  -p 8000:8000 \
  --name runowl \
  runowl</code></pre>
</div>

<h3>Reverse Proxy (nginx)</h3>
<p>Put RunOwl behind nginx to handle TLS termination — required for GitHub webhooks which only deliver to HTTPS endpoints.</p>

<div class="code-block">
	<div class="code-block-header">/etc/nginx/sites-available/runowl</div>
	<pre><code>server &#123;
    listen 443 ssl;
    server_name runowl.your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/runowl.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/runowl.your-domain.com/privkey.pem;

    location / &#123;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    &#125;
&#125;</code></pre>
</div>

<div class="callout warning">
	<span class="callout-icon">⚠️</span>
	<p>GitHub requires webhook endpoints to use HTTPS. Get a free TLS certificate from Let's Encrypt: <code>certbot --nginx -d runowl.your-domain.com</code></p>
</div>

<h2>Updating</h2>

<div class="code-block">
	<div class="code-block-header">terminal</div>
	<pre><code>cd /opt/runowl
git pull origin main
uv sync
sudo systemctl restart runowl</code></pre>
</div>

<h2>Health Monitoring</h2>
<p>Use the <code>/health</code> endpoint for uptime monitoring:</p>

<div class="code-block">
	<div class="code-block-header">terminal</div>
	<pre><code>curl https://runowl.your-domain.com/health
<span style="color:var(--green)"># → &#123;"status": "ok", "version": "0.1.0"&#125;</span></code></pre>
</div>

<p>Configure your monitoring tool (UptimeRobot, Datadog, etc.) to check this endpoint every minute.</p>

<h2>Security Hardening</h2>
<ul>
	<li><strong>Always set <code>GITHUB_WEBHOOK_SECRET</code></strong> — without it, anyone can trigger reviews by sending fake webhook payloads</li>
	<li><strong>Use a dedicated GitHub Token</strong> — create a service account with minimum required scopes</li>
	<li><strong>Firewall</strong> — restrict port 8000 to localhost; only expose via nginx on 443</li>
	<li><strong>Rate limiting</strong> — consider adding nginx rate limiting to the webhook endpoint</li>
	<li><strong>Log rotation</strong> — configure logrotate for application logs</li>
</ul>

<h2>Troubleshooting</h2>

<h3>Webhook not triggering</h3>
<ul>
	<li>Check the webhook delivery log in GitHub: repo → Settings → Webhooks → Recent Deliveries</li>
	<li>Verify the server is reachable: <code>curl -X POST https://your-server/webhook/github</code> should return <code>422</code> (not 404/502)</li>
	<li>Check that <code>GITHUB_WEBHOOK_SECRET</code> matches exactly what you set in GitHub</li>
</ul>

<h3>Reviews failing silently</h3>
<ul>
	<li>Check server logs: <code>journalctl -u runowl -f</code></li>
	<li>Verify <code>GEMINI_API_KEY</code> is valid: <code>curl https://generativelanguage.googleapis.com/v1/models?key=$GEMINI_API_KEY</code></li>
	<li>Verify <code>GITHUB_TOKEN</code> has correct scopes: <code>curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user</code></li>
</ul>

</div>
</DocsLayout>
