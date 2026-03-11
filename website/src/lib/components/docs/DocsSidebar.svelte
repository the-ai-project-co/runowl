<script lang="ts">
	import { Github, BookOpen, Terminal, Webhook, BrainCircuit, ShieldCheck, Settings, Server, Code2, ChevronRight } from 'lucide-svelte';

	export let currentPath: string = '';
	export let mobileOpen = false;

	const nav = [
		{
			group: 'Overview',
			items: [
				{ href: '/docs/getting-started', label: 'Getting Started', Icon: BookOpen },
			]
		},
		{
			group: 'Usage',
			items: [
				{ href: '/docs/cli-reference', label: 'CLI Reference', Icon: Terminal },
				{ href: '/docs/github-integration', label: 'GitHub Integration', Icon: Github },
			]
		},
		{
			group: 'Deep Dives',
			items: [
				{ href: '/docs/how-it-works', label: 'How It Works', Icon: BrainCircuit },
				{ href: '/docs/security-analysis', label: 'Security Analysis', Icon: ShieldCheck },
			]
		},
		{
			group: 'Reference',
			items: [
				{ href: '/docs/configuration', label: 'Configuration', Icon: Settings },
				{ href: '/docs/self-hosting', label: 'Self-Hosting', Icon: Server },
				{ href: '/docs/api-reference', label: 'API Reference', Icon: Code2 },
			]
		},
	];

	function isActive(href: string): boolean {
		return currentPath === href || currentPath.startsWith(href + '/');
	}
</script>

<aside class="sidebar" class:open={mobileOpen}>
	<div class="sidebar-header">
		<a href="/" class="back-home">
			<svg width="20" height="20" viewBox="0 0 28 28" fill="none">
				<circle cx="14" cy="14" r="13" stroke="var(--accent)" stroke-width="1.5"/>
				<circle cx="14" cy="14" r="5" fill="var(--accent)" opacity="0.9"/>
			</svg>
			<span>Run<span class="acc">Owl</span></span>
		</a>
		<span class="docs-badge">Docs</span>
	</div>

	<nav class="sidebar-nav">
		{#each nav as section}
			<div class="nav-section">
				<div class="nav-group-label">{section.group}</div>
				{#each section.items as item}
					<a
						href={item.href}
						class="nav-item"
						class:active={isActive(item.href)}
					>
						<svelte:component this={item.Icon} size={14} />
						{item.label}
						{#if isActive(item.href)}
							<ChevronRight size={12} class="active-chevron" />
						{/if}
					</a>
				{/each}
			</div>
		{/each}
	</nav>

	<div class="sidebar-footer">
		<a href="https://github.com/the-ai-project-co/RunOwl" target="_blank" class="gh-link">
			<Github size={14} />
			View on GitHub
		</a>
	</div>
</aside>

<style>
	.sidebar {
		width: 240px;
		flex-shrink: 0;
		border-right: 1px solid var(--border);
		display: flex;
		flex-direction: column;
		background: var(--surface);
		height: 100vh;
		position: sticky;
		top: 0;
		overflow-y: auto;
	}

	.sidebar-header {
		padding: 1.25rem 1.25rem 1rem;
		border-bottom: 1px solid var(--border);
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.back-home {
		display: flex; align-items: center; gap: 0.5rem;
		font-weight: 700; font-size: 1rem; color: var(--text);
		text-decoration: none;
	}
	.acc { color: var(--accent); }

	.docs-badge {
		font-size: 0.65rem; font-weight: 700;
		padding: 0.15rem 0.5rem; border-radius: 4px;
		background: var(--accent-glow);
		border: 1px solid rgba(124,106,247,0.25);
		color: var(--accent);
		text-transform: uppercase; letter-spacing: 0.06em;
	}

	.sidebar-nav {
		flex: 1;
		padding: 1rem 0;
		overflow-y: auto;
	}

	.nav-section {
		margin-bottom: 1.5rem;
	}

	.nav-group-label {
		font-size: 0.65rem; font-weight: 700;
		text-transform: uppercase; letter-spacing: 0.1em;
		color: var(--muted);
		padding: 0 1.25rem;
		margin-bottom: 0.35rem;
	}

	.nav-item {
		display: flex; align-items: center; gap: 0.6rem;
		padding: 0.45rem 1.25rem;
		font-size: 0.875rem;
		color: var(--muted);
		text-decoration: none;
		transition: color 0.15s, background 0.15s;
		position: relative;
	}
	.nav-item:hover { color: var(--text); background: var(--surface-2); }
	.nav-item.active {
		color: var(--accent);
		background: var(--accent-glow);
		font-weight: 500;
	}
	.nav-item.active::before {
		content: '';
		position: absolute; left: 0; top: 0; bottom: 0;
		width: 2px; background: var(--accent);
	}
	:global(.active-chevron) { margin-left: auto; color: var(--accent); }

	.sidebar-footer {
		padding: 1rem 1.25rem;
		border-top: 1px solid var(--border);
	}
	.gh-link {
		display: flex; align-items: center; gap: 0.5rem;
		font-size: 0.8rem; color: var(--muted);
		text-decoration: none;
		transition: color 0.2s;
	}
	.gh-link:hover { color: var(--text); }

	@media (max-width: 768px) {
		.sidebar {
			position: fixed; left: -240px; top: 0; z-index: 100;
			transition: left 0.25s ease;
		}
		.sidebar.open {
			left: 0;
			box-shadow: 4px 0 30px rgba(0,0,0,0.4);
		}
	}
</style>
