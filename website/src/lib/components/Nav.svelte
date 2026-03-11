<script lang="ts">
	import { theme, toggleTheme } from '$lib/stores/theme';
	import { Sun, Moon, Github, ArrowRight } from 'lucide-svelte';

	let scrolled = false;

	if (typeof window !== 'undefined') {
		window.addEventListener('scroll', () => {
			scrolled = window.scrollY > 20;
		});
	}
</script>

<nav class:scrolled>
	<div class="nav-inner">

		<!-- Logo -->
		<a href="/" class="logo-mark">
			<span class="logo-icon">
				<svg width="28" height="28" viewBox="0 0 28 28" fill="none">
					<circle cx="14" cy="14" r="13" stroke="var(--accent)" stroke-width="1.5"/>
					<circle cx="14" cy="14" r="5" fill="var(--accent)" opacity="0.9"/>
					<circle cx="14" cy="14" r="9" stroke="var(--accent)" stroke-width="0.75" stroke-dasharray="2 3"/>
				</svg>
			</span>
			<span class="logo-text">Run<span class="logo-accent">Owl</span></span>
		</a>

		<!-- Desktop links -->
		<div class="nav-links">
			<a href="#features" class="nav-link">Features</a>
			<a href="#how-it-works" class="nav-link">How it works</a>
			<a href="#pricing" class="nav-link">Pricing</a>
			<a href="/docs/getting-started" class="nav-link">Docs</a>
		</div>

		<!-- Actions -->
		<div class="nav-actions">
			<button class="theme-toggle" on:click={toggleTheme} aria-label="Toggle theme">
				{#if $theme === 'dark'}
					<Sun size={15} />
				{:else}
					<Moon size={15} />
				{/if}
			</button>

			<a href="https://github.com/the-ai-project-co/RunOwl" class="btn-ghost" target="_blank">
				<Github size={15} />
				GitHub
			</a>

			<a href="#pricing" class="btn-primary">
				Get started
				<ArrowRight size={13} />
			</a>
		</div>
	</div>
</nav>

<style>
	nav {
		position: fixed; top: 0; left: 0; right: 0; z-index: 50;
		border-bottom: 1px solid transparent;
		transition: background 0.3s, border-color 0.3s;
	}
	nav.scrolled {
		background: rgba(10, 10, 15, 0.85);
		backdrop-filter: blur(12px);
		-webkit-backdrop-filter: blur(12px);
		border-bottom-color: var(--border);
	}
	:global([data-theme='light']) nav.scrolled {
		background: rgba(250, 250, 250, 0.85);
	}

	.nav-inner {
		width: 100%; max-width: 80rem;
		margin-left: auto; margin-right: auto;
		padding: 0 1.5rem;
		height: 4rem;
		display: flex; align-items: center; justify-content: space-between;
	}

	.logo-mark {
		display: flex; align-items: center; gap: 0.5rem;
		text-decoration: none;
	}
	.logo-text {
		font-weight: 700; letter-spacing: -0.02em;
		font-size: 1.1rem; color: var(--text);
	}
	.logo-accent { color: var(--accent); }

	.nav-links {
		display: flex; align-items: center; gap: 2rem;
		font-size: 0.875rem;
	}
	@media (max-width: 768px) { .nav-links { display: none; } }

	.nav-link {
		color: var(--muted); text-decoration: none;
		transition: color 0.2s;
	}
	.nav-link:hover { color: var(--text); }

	.nav-actions {
		display: flex; align-items: center; gap: 0.75rem;
	}

	.theme-toggle {
		display: flex; align-items: center; justify-content: center;
		width: 32px; height: 32px; border-radius: 8px;
		background: transparent;
		border: 1px solid var(--border);
		color: var(--muted);
		cursor: pointer;
		transition: all 0.2s;
	}
	.theme-toggle:hover { color: var(--text); border-color: var(--accent); }

	.btn-ghost {
		display: flex; align-items: center; gap: 0.5rem;
		color: var(--muted); text-decoration: none;
		padding: 0.4rem 0.75rem;
		border-radius: 6px;
		font-size: 0.875rem;
		border: 1px solid var(--border);
		transition: all 0.2s;
	}
	.btn-ghost:hover { color: var(--text); border-color: var(--muted); }
	@media (max-width: 768px) { .btn-ghost { display: none; } }

	.btn-primary {
		display: flex; align-items: center; gap: 0.375rem;
		background: var(--accent);
		color: #fff; text-decoration: none;
		padding: 0.45rem 1rem;
		border-radius: 6px;
		font-size: 0.875rem;
		font-weight: 600;
		transition: opacity 0.2s, transform 0.2s;
	}
	.btn-primary:hover { opacity: 0.9; transform: translateY(-1px); }
</style>
