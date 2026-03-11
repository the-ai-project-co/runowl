<script lang="ts">
	import { onMount } from 'svelte';
	import { ArrowRight, Github } from 'lucide-svelte';

	let visible = false;
	onMount(() => { setTimeout(() => (visible = true), 100); });
</script>

<section class="hero">
	<div class="grid-bg" aria-hidden="true"></div>
	<div class="orb orb-1" aria-hidden="true"></div>
	<div class="orb orb-2" aria-hidden="true"></div>

	<div class="hero-inner px-6 text-center" class:visible>
		<div class="badge">
			<span class="badge-dot"></span>
			Open-source · MIT · v0.1.0
		</div>

		<h1 class="hero-title">
			Code review that actually<br />
			<em>reads</em> your code
		</h1>

		<p class="hero-sub">
			RunOwl is an AI agent that reviews GitHub PRs, finds bugs and security issues
			with severity levels, and posts findings as PR comments — automatically.
		</p>

		<div class="hero-actions">
			<a href="#pricing" class="cta-primary">
				Start for free
				<ArrowRight size={16} />
			</a>
			<a href="https://github.com/the-ai-project-co/RunOwl" target="_blank" class="cta-secondary">
				<Github size={16} />
				View on GitHub
			</a>
		</div>

		<!-- Terminal demo -->
		<div class="terminal">
			<div class="terminal-bar">
				<div class="dots">
					<span class="dot red"></span>
					<span class="dot yellow"></span>
					<span class="dot green"></span>
				</div>
				<span class="terminal-title">Terminal</span>
			</div>
			<div class="terminal-body">
				<div class="line">
					<span class="prompt">$</span>
					<span class="cmd">npx runowl review --url https://github.com/owner/repo/pull/42</span>
				</div>
				<div class="line output">
					<span class="check">✓</span> Fetching PR <span class="accent">#42</span> — "Add user authentication"
				</div>
				<div class="line output">
					<span class="check">✓</span> Reasoning loop: <span class="hi-green">12 iterations</span>
				</div>
				<div class="spacer"></div>
				<div class="line finding">
					<span class="sev p0">P0</span>
					<span class="file">src/auth.py:47</span>
					<span class="fdesc">— Hardcoded JWT secret exposed</span>
				</div>
				<div class="line finding">
					<span class="sev p1">P1</span>
					<span class="file">src/routes.py:103</span>
					<span class="fdesc">— Missing auth on /admin endpoint</span>
				</div>
				<div class="line finding">
					<span class="sev p2">P2</span>
					<span class="file">src/db.py:29</span>
					<span class="fdesc">— SQL query uses string concat</span>
				</div>
				<div class="spacer"></div>
				<div class="line output">
					<span class="cross">✗</span> Check Run failed · <span class="dim">2 blocking findings</span>
				</div>
			</div>
		</div>
	</div>
</section>

<style>
	.hero {
		position: relative;
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		align-items: stretch;
		justify-content: center;
		overflow: hidden;
		padding-top: 4rem;
	}

	.grid-bg {
		position: absolute; inset: 0;
		background-image:
			linear-gradient(var(--border) 1px, transparent 1px),
			linear-gradient(90deg, var(--border) 1px, transparent 1px);
		background-size: 60px 60px;
		opacity: 0.3;
		mask-image: radial-gradient(ellipse 80% 60% at 50% 40%, black, transparent);
	}

	.orb {
		position: absolute; border-radius: 50%;
		filter: blur(80px); pointer-events: none;
	}
	.orb-1 {
		width: 600px; height: 600px;
		background: radial-gradient(circle, rgba(124,106,247,0.12) 0%, transparent 70%);
		top: -100px; left: 50%; transform: translateX(-50%);
	}
	.orb-2 {
		width: 400px; height: 400px;
		background: radial-gradient(circle, rgba(56,189,248,0.08) 0%, transparent 70%);
		bottom: 0; right: 10%;
	}

	.hero-inner {
		width: 100%;
		max-width: 64rem;
		margin-left: auto;
		margin-right: auto;
		text-align: center;
		position: relative; z-index: 1;
		padding: 5rem 1.5rem;
		opacity: 0; transform: translateY(20px);
		transition: opacity 0.8s ease, transform 0.8s ease;
	}
	.hero-inner.visible { opacity: 1; transform: translateY(0); }

	.badge {
		display: inline-flex; align-items: center; gap: 0.5rem;
		padding: 0.35rem 1rem; border-radius: 99px;
		border: 1px solid var(--border);
		background: var(--surface);
		font-size: 0.8rem; color: var(--muted);
		margin-bottom: 2rem;
	}
	.badge-dot {
		width: 6px; height: 6px; border-radius: 50%;
		background: var(--green);
		box-shadow: 0 0 6px var(--green);
	}

	.hero-title {
		font-size: clamp(2.5rem, 6vw, 4.5rem);
		font-weight: 800;
		line-height: 1.1;
		letter-spacing: -0.03em;
		margin-bottom: 1.5rem;
		color: var(--text);
		font-family: 'Inter', sans-serif;
	}
	.hero-title em { font-style: normal; color: var(--accent); }

	.hero-sub {
		font-size: 1.15rem;
		color: var(--muted);
		max-width: 560px;
		margin: 0 auto 2.5rem;
		line-height: 1.7;
	}

	.hero-actions {
		display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap;
		margin-bottom: 3.5rem;
	}

	.cta-primary {
		display: inline-flex; align-items: center; gap: 0.5rem;
		background: var(--accent); color: #fff;
		padding: 0.75rem 1.5rem; border-radius: 8px;
		font-weight: 600; font-size: 0.95rem;
		transition: transform 0.2s, box-shadow 0.2s;
		box-shadow: 0 0 30px rgba(124, 106, 247, 0.3);
	}
	.cta-primary:hover { transform: translateY(-2px); box-shadow: 0 0 40px rgba(124, 106, 247, 0.5); }

	.cta-secondary {
		display: inline-flex; align-items: center; gap: 0.5rem;
		background: var(--surface); color: var(--text);
		padding: 0.75rem 1.5rem; border-radius: 8px;
		font-weight: 600; font-size: 0.95rem;
		border: 1px solid var(--border);
		transition: all 0.2s;
	}
	.cta-secondary:hover { border-color: var(--muted); transform: translateY(-1px); }

	.terminal {
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 12px;
		overflow: hidden;
		text-align: left;
		max-width: 640px;
		margin: 0 auto;
		box-shadow: 0 24px 80px rgba(0,0,0,0.4);
	}
	.terminal-bar {
		background: var(--surface-2);
		padding: 0.75rem 1rem;
		display: flex; align-items: center; gap: 0.75rem;
		border-bottom: 1px solid var(--border);
	}
	.dots { display: flex; gap: 6px; }
	.dot { width: 12px; height: 12px; border-radius: 50%; }
	.dot.red { background: #ff5f57; }
	.dot.yellow { background: #febc2e; }
	.dot.green { background: #28c840; }
	.terminal-title { font-size: 0.8rem; color: var(--muted); flex: 1; text-align: center; }

	.terminal-body {
		padding: 1.25rem 1.5rem;
		font-family: 'SF Mono', 'Fira Code', monospace;
		font-size: 0.82rem;
		line-height: 1.8;
	}
	.line { display: flex; gap: 0.5rem; align-items: baseline; }
	.finding { gap: 0.4rem; }
	.spacer { height: 0.4rem; }
	.prompt { color: var(--muted); }
	.cmd { color: var(--green); }
	.output { color: var(--muted); }
	.check { color: var(--green); }
	.cross { color: var(--red); }
	.dim { color: var(--border); }
	.accent { color: var(--accent); }
	.hi-green { color: var(--green); }
	.file { color: var(--accent-2); }
	.fdesc { color: var(--muted); }

	.sev {
		font-size: 0.65rem; font-weight: 700;
		padding: 0.1rem 0.35rem; border-radius: 3px;
		color: #fff; flex-shrink: 0;
	}
	.sev.p0 { background: var(--red); }
	.sev.p1 { background: var(--yellow); color: #000; }
	.sev.p2 { background: var(--muted); }
</style>
