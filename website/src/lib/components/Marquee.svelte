<script lang="ts">
	import {
		Code2, Braces, Cpu, Zap, Coffee, Gem, Globe, Target,
		CircleDot, Apple, Layers, Leaf, Bolt, Triangle, Server, Rocket
	} from 'lucide-svelte';

	const items = [
		{ name: 'Python',     Icon: Code2 },
		{ name: 'TypeScript', Icon: Braces },
		{ name: 'Go',         Icon: Cpu },
		{ name: 'Rust',       Icon: Zap },
		{ name: 'Java',       Icon: Coffee },
		{ name: 'Ruby',       Icon: Gem },
		{ name: 'PHP',        Icon: Globe },
		{ name: 'C#',         Icon: Target },
		{ name: 'Kotlin',     Icon: CircleDot },
		{ name: 'Swift',      Icon: Apple },
		{ name: 'React',      Icon: Layers },
		{ name: 'Django',     Icon: Leaf },
		{ name: 'FastAPI',    Icon: Bolt },
		{ name: 'Next.js',    Icon: Triangle },
		{ name: 'Node.js',    Icon: Server },
		{ name: 'Rails',      Icon: Rocket },
	];

	const doubled = [...items, ...items];
</script>

<div class="marquee-wrapper" aria-hidden="true">
	<div class="marquee-fade-left"></div>
	<div class="marquee-fade-right"></div>
	<div class="marquee-track">
		<div class="animate-marquee">
			{#each doubled as item}
				<div class="marquee-item">
					<svelte:component this={item.Icon} size={15} />
					<span class="item-name">{item.name}</span>
				</div>
			{/each}
		</div>
	</div>
</div>

<div class="marquee-label">
	Works with every language and framework your team uses
</div>

<style>
	.marquee-wrapper {
		position: relative;
		overflow: hidden;
		padding: 1.5rem 0;
		border-top: 1px solid var(--border);
		border-bottom: 1px solid var(--border);
		background: var(--surface);
	}

	.marquee-fade-left,
	.marquee-fade-right {
		position: absolute; top: 0; bottom: 0; width: 120px; z-index: 2;
		pointer-events: none;
	}
	.marquee-fade-left {
		left: 0;
		background: linear-gradient(90deg, var(--surface), transparent);
	}
	.marquee-fade-right {
		right: 0;
		background: linear-gradient(-90deg, var(--surface), transparent);
	}

	.marquee-track { overflow: hidden; }

	.marquee-item {
		display: inline-flex; align-items: center; gap: 0.5rem;
		padding: 0.4rem 1.5rem;
		color: var(--muted);
		font-size: 0.85rem; font-weight: 500;
		white-space: nowrap;
		border-right: 1px solid var(--border);
		transition: color 0.2s;
	}
	.marquee-item:hover { color: var(--text); }

	.marquee-label {
		text-align: center;
		color: var(--muted);
		font-size: 0.82rem;
		padding: 1rem;
		border-bottom: 1px solid var(--border);
		background: var(--surface);
	}
</style>
