<script lang="ts">
	import { Github, Heart } from 'lucide-svelte';

	const links = {
		Product: [
			{ label: 'Features',   href: '#features' },
			{ label: 'How it works', href: '#how-it-works' },
			{ label: 'Pricing',    href: '#pricing' },
			{ label: 'Changelog',  href: 'https://github.com/the-ai-project-co/RunOwl/blob/main/CHANGELOG.md' },
		],
		Developers: [
			{ label: 'Documentation', href: '/docs/getting-started' },
			{ label: 'Installation',  href: '/docs/getting-started' },
			{ label: 'Contributing',  href: 'https://github.com/the-ai-project-co/RunOwl/blob/main/CONTRIBUTING.md' },
			{ label: 'GitHub',        href: 'https://github.com/the-ai-project-co/RunOwl' },
		],
		Company: [
			{ label: 'Security', href: 'mailto:security@runowl.ai' },
			{ label: 'Privacy',  href: '#' },
			{ label: 'Terms',    href: '#' },
			{ label: 'Contact',  href: 'mailto:hello@runowl.ai' },
		],
	};
</script>

<footer class="site-footer">
	<div class="section-wrap">
		<div class="footer-top">
			<div class="footer-brand">
				<a href="/" class="logo">
					<svg width="22" height="22" viewBox="0 0 28 28" fill="none">
						<circle cx="14" cy="14" r="13" stroke="var(--accent)" stroke-width="1.5"/>
						<circle cx="14" cy="14" r="5" fill="var(--accent)" opacity="0.9"/>
						<circle cx="14" cy="14" r="9" stroke="var(--accent)" stroke-width="0.75" stroke-dasharray="2 3"/>
					</svg>
					<span>Run<span class="accent">Owl</span></span>
				</a>
				<p class="brand-tagline">One agent. Reviews, tests, ships.</p>
				<div class="social-links">
					<a href="https://github.com/the-ai-project-co/RunOwl" target="_blank" aria-label="GitHub">
						<Github size={16} />
					</a>
				</div>
			</div>

			{#each Object.entries(links) as [category, items]}
				<div class="footer-col">
					<h4>{category}</h4>
					<ul>
						{#each items as link}
							<li><a href={link.href}>{link.label}</a></li>
						{/each}
					</ul>
				</div>
			{/each}
		</div>

		<div class="footer-bottom">
			<span>MIT License · © 2026 RunOwl</span>
			<span class="built-with">
				Built with <Heart size={12} class="heart" /> for developers
			</span>
		</div>
	</div>
</footer>

<style>
	.site-footer { border-top: 1px solid var(--border); padding: 4rem 0 2rem; }

	.footer-top {
		display: grid; grid-template-columns: 2fr 1fr 1fr 1fr;
		gap: 3rem; margin-bottom: 3rem;
	}
	@media (max-width: 768px) { .footer-top { grid-template-columns: 1fr 1fr; gap: 2rem; } }

	.logo {
		display: inline-flex; align-items: center; gap: 0.5rem;
		font-size: 1.05rem; font-weight: 700; color: var(--text); margin-bottom: 0.75rem;
	}
	.accent { color: var(--accent); }
	.brand-tagline { font-size: 0.875rem; color: var(--muted); margin-bottom: 1.25rem; }

	.social-links { display: flex; gap: 0.75rem; }
	.social-links a {
		color: var(--muted); width: 32px; height: 32px; border-radius: 8px;
		border: 1px solid var(--border);
		display: flex; align-items: center; justify-content: center;
		transition: all 0.2s;
	}
	.social-links a:hover { color: var(--text); border-color: var(--muted); }

	.footer-col h4 {
		font-size: 0.78rem; font-weight: 700;
		text-transform: uppercase; letter-spacing: 0.08em;
		color: var(--text); margin-bottom: 1rem;
	}
	.footer-col ul { list-style: none; display: flex; flex-direction: column; gap: 0.6rem; }
	.footer-col a { font-size: 0.875rem; color: var(--muted); transition: color 0.2s; }
	.footer-col a:hover { color: var(--text); }

	.footer-bottom {
		border-top: 1px solid var(--border); padding-top: 1.5rem;
		display: flex; justify-content: space-between; align-items: center;
		font-size: 0.8rem; color: var(--muted); flex-wrap: wrap; gap: 0.5rem;
	}
	.built-with { display: flex; align-items: center; gap: 0.35rem; }
	:global(.heart) { color: var(--red); }
</style>
