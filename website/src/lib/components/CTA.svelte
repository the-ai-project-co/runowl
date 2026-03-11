<script lang="ts">
	import { Github, BookOpen, Terminal } from 'lucide-svelte';
</script>

<section class="cta-section">
	<div class="cta-bg" aria-hidden="true"></div>
	<div class="cta-content">
		<h2 class="cta-title">Start reviewing PRs in 30 seconds</h2>
		<p class="cta-sub">No sign-up required. Free forever for open-source.</p>

		<div class="cta-command">
			<Terminal size={14} class="term-icon" />
			<code>npx runowl review --url &lt;github-pr-url&gt;</code>
		</div>

		<div class="cta-actions">
			<a href="https://github.com/the-ai-project-co/RunOwl" target="_blank" class="cta-primary">
				<Github size={17} />
				Star on GitHub
			</a>
			<a href="/docs/getting-started" class="cta-secondary">
				<BookOpen size={17} />
				Read the docs
			</a>
		</div>
	</div>
</section>

<style>
	.cta-section { position: relative; padding: 7rem 0; overflow: hidden; }
	.cta-bg {
		position: absolute; inset: 0;
		background: radial-gradient(ellipse 60% 60% at 50% 50%, rgba(124,106,247,0.08) 0%, transparent 70%);
	}
	.cta-content {
		position: relative; z-index: 1;
		width: 100%; max-width: 48rem;
		margin-left: auto; margin-right: auto;
		padding: 0 1.5rem;
		text-align: center;
	}

	.cta-title {
		font-size: clamp(2rem, 4.5vw, 3.25rem);
		font-weight: 800; letter-spacing: -0.03em;
		margin-bottom: 1rem; color: var(--text);
	}
	.cta-sub { font-size: 1.1rem; color: var(--muted); margin-bottom: 2rem; }

	.cta-command {
		display: inline-flex; align-items: center; gap: 0.6rem;
		background: var(--surface); border: 1px solid var(--border);
		border-radius: 8px; padding: 0.75rem 1.5rem; margin-bottom: 2rem;
	}
	:global(.term-icon) { color: var(--muted); }
	.cta-command code {
		font-family: 'SF Mono', 'Fira Code', monospace;
		font-size: 0.9rem; color: var(--green);
	}

	.cta-actions { display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; }

	.cta-primary {
		display: inline-flex; align-items: center; gap: 0.5rem;
		background: var(--text); color: var(--bg);
		padding: 0.75rem 1.5rem; border-radius: 8px;
		font-weight: 600; font-size: 0.95rem;
		transition: opacity 0.2s, transform 0.2s;
	}
	.cta-primary:hover { opacity: 0.9; transform: translateY(-1px); }

	.cta-secondary {
		display: inline-flex; align-items: center; gap: 0.5rem;
		color: var(--muted); padding: 0.75rem 1.5rem; border-radius: 8px;
		font-weight: 600; font-size: 0.95rem;
		border: 1px solid var(--border); transition: all 0.2s;
	}
	.cta-secondary:hover { color: var(--text); border-color: var(--muted); }
</style>
