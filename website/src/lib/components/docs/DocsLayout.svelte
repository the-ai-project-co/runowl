<script lang="ts">
	import DocsSidebar from './DocsSidebar.svelte';
	import { Menu, X } from 'lucide-svelte';
	import { page } from '$app/stores';

	export let title: string;
	export let description: string = '';

	let mobileOpen = false;

	$: currentPath = $page.url.pathname;
</script>

<svelte:head>
	<title>{title} — RunOwl Docs</title>
	{#if description}
		<meta name="description" content={description} />
	{/if}
</svelte:head>

<div class="docs-shell">
	<DocsSidebar {currentPath} bind:mobileOpen />

	{#if mobileOpen}
		<button class="backdrop" on:click={() => mobileOpen = false} aria-label="Close sidebar"></button>
	{/if}

	<div class="docs-body">
		<header class="mobile-header">
			<button class="menu-btn" on:click={() => mobileOpen = !mobileOpen} aria-label="Toggle menu">
				{#if mobileOpen}
					<X size={18} />
				{:else}
					<Menu size={18} />
				{/if}
			</button>
			<a href="/" class="mobile-logo">Run<span>Owl</span></a>
			<a href="/docs/getting-started" class="mobile-docs-label">Docs</a>
		</header>

		<main class="docs-main">
			<div class="docs-content">
				<slot />
			</div>
		</main>
	</div>
</div>

<style>
	.docs-shell {
		display: flex;
		min-height: 100vh;
		background: var(--bg);
	}

	.backdrop {
		display: none;
		position: fixed; inset: 0; z-index: 99;
		background: rgba(0,0,0,0.5);
		border: none; cursor: pointer;
	}
	@media (max-width: 768px) {
		.backdrop { display: block; }
	}

	.docs-body {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
	}

	.mobile-header {
		display: none;
		align-items: center;
		gap: 1rem;
		padding: 0 1rem;
		height: 3.5rem;
		border-bottom: 1px solid var(--border);
		background: var(--surface);
		position: sticky; top: 0; z-index: 50;
	}
	@media (max-width: 768px) { .mobile-header { display: flex; } }

	.menu-btn {
		background: none; border: 1px solid var(--border);
		border-radius: 6px; width: 32px; height: 32px;
		display: flex; align-items: center; justify-content: center;
		color: var(--muted); cursor: pointer;
	}
	.mobile-logo {
		font-weight: 700; font-size: 1rem; color: var(--text);
		text-decoration: none;
	}
	.mobile-logo span { color: var(--accent); }
	.mobile-docs-label {
		margin-left: auto; font-size: 0.8rem; color: var(--muted);
		text-decoration: none;
	}

	.docs-main {
		flex: 1;
		overflow-y: auto;
	}

	.docs-content {
		max-width: 780px;
		margin: 0 auto;
		padding: 3rem 2.5rem 6rem;
	}

	@media (max-width: 640px) {
		.docs-content { padding: 2rem 1.25rem 4rem; }
	}
</style>
