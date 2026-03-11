<script lang="ts">
	import { onMount } from 'svelte';
	import { BrainCircuit, ShieldCheck, Building2, GitPullRequestArrow, MessageSquareCode, Container } from 'lucide-svelte';

	const features = [
		{
			Icon: BrainCircuit,
			title: 'Recursive Reasoning Loop',
			description: 'Reads the diff, fetches related files for context, refines its analysis. Finds bugs that only make sense when you see the full picture.',
			tag: 'Free',
			paid: false,
		},
		{
			Icon: ShieldCheck,
			title: 'Security Analysis',
			description: 'Hardcoded secrets, SQL injection, XSS, missing auth — free. Full OWASP Top 10, JWT flaws, crypto failures — paid.',
			tag: 'Free + Paid',
			paid: false,
		},
		{
			Icon: Building2,
			title: 'Architecture Analysis',
			description: 'SOLID principle violations, god objects, deep nesting, feature envy — catches design problems before they calcify.',
			tag: 'Team',
			paid: true,
		},
		{
			Icon: GitPullRequestArrow,
			title: 'GitHub Check Runs',
			description: 'Creates a check run on every PR. Turns red on P0/P1 findings. Blocks merges when critical issues are found.',
			tag: 'Team',
			paid: true,
		},
		{
			Icon: MessageSquareCode,
			title: 'Interactive Q&A',
			description: 'Ask questions about the PR in natural language. "Any race conditions in this file?" RunOwl answers with citations.',
			tag: 'Free',
			paid: false,
		},
		{
			Icon: Container,
			title: 'Sandboxed Execution',
			description: 'All agent tool calls run in a Deno sandbox. No network access, no file writes, no shell. Your code stays safe.',
			tag: 'Free',
			paid: false,
		},
	];

	let cards: HTMLElement[] = [];
	let visible: boolean[] = new Array(features.length).fill(false);

	onMount(() => {
		const observer = new IntersectionObserver(
			(entries) => {
				entries.forEach((entry) => {
					if (entry.isIntersecting) {
						const idx = cards.indexOf(entry.target as HTMLElement);
						if (idx !== -1) setTimeout(() => { visible[idx] = true; visible = [...visible]; }, idx * 80);
					}
				});
			},
			{ threshold: 0.1 }
		);
		cards.forEach((c) => c && observer.observe(c));
		return () => observer.disconnect();
	});
</script>

<section id="features" class="features-section">
	<div class="section-wrap">
		<div class="section-header">
			<div class="section-eyebrow">Features</div>
			<h2 class="section-title">Everything you need to ship with confidence</h2>
			<p class="section-sub">Free for individuals and open-source. Paid deep analysis for teams.</p>
		</div>

		<div class="features-grid">
			{#each features as feature, i}
				<div
					class="feature-card"
					class:visible={visible[i]}
					bind:this={cards[i]}
				>
					<div class="feature-icon">
						<svelte:component this={feature.Icon} size={20} />
					</div>
					<div class="feature-tag" class:paid={feature.paid}>{feature.tag}</div>
					<h3>{feature.title}</h3>
					<p>{feature.description}</p>
				</div>
			{/each}
		</div>
	</div>
</section>

<style>
	.features-section { padding: 6rem 0; }

	.section-header { text-align: center; margin-bottom: 3.5rem; }
	.section-eyebrow {
		font-size: 0.75rem; font-weight: 700;
		letter-spacing: 0.12em; text-transform: uppercase;
		color: var(--accent); margin-bottom: 0.75rem;
	}
	.section-title {
		font-size: clamp(1.75rem, 3.5vw, 2.75rem);
		font-weight: 800; letter-spacing: -0.02em;
		margin-bottom: 0.75rem; color: var(--text);
	}
	.section-sub { font-size: 1rem; color: var(--muted); }

	.features-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
		gap: 1.25rem;
	}

	.feature-card {
		background: var(--surface); border: 1px solid var(--border);
		border-radius: 12px; padding: 1.75rem;
		opacity: 0; transform: translateY(20px);
		transition: opacity 0.5s ease, transform 0.5s ease, border-color 0.2s, box-shadow 0.2s;
	}
	.feature-card.visible { opacity: 1; transform: translateY(0); }
	.feature-card:hover { border-color: var(--accent); box-shadow: 0 0 30px var(--accent-glow); }

	.feature-icon {
		color: var(--accent); margin-bottom: 1rem;
		width: 40px; height: 40px;
		display: flex; align-items: center; justify-content: center;
		background: var(--accent-glow); border-radius: 8px;
		border: 1px solid rgba(124, 106, 247, 0.2);
	}

	.feature-tag {
		display: inline-block;
		font-size: 0.7rem; font-weight: 600;
		padding: 0.15rem 0.5rem; border-radius: 4px;
		background: rgba(74, 222, 128, 0.1); color: var(--green);
		border: 1px solid rgba(74, 222, 128, 0.2);
		margin-bottom: 0.75rem;
		text-transform: uppercase; letter-spacing: 0.06em;
	}
	.feature-tag.paid {
		background: rgba(124, 106, 247, 0.1); color: var(--accent);
		border-color: rgba(124, 106, 247, 0.2);
	}

	.feature-card h3 { font-size: 1rem; font-weight: 600; margin-bottom: 0.5rem; color: var(--text); }
	.feature-card p { font-size: 0.875rem; color: var(--muted); line-height: 1.65; }
</style>
