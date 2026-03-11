<script lang="ts">
	import { onMount } from 'svelte';
	import { BookOpen, Lightbulb, FolderSearch, RefreshCw, SendHorizonal } from 'lucide-svelte';

	const steps = [
		{
			Icon: BookOpen,
			num: '01',
			title: 'Read the PR',
			description: 'Fetches PR metadata, diff, and description from the GitHub API.',
			detail: 'Parses every added line, builds context about what changed and why.',
		},
		{
			Icon: Lightbulb,
			num: '02',
			title: 'Reason',
			description: 'Gemini analyses the diff and decides what context it needs.',
			detail: 'The model identifies function calls, imports, and patterns that require deeper investigation.',
		},
		{
			Icon: FolderSearch,
			num: '03',
			title: 'Fetch Context',
			description: 'Reads related files, searches code, lists directories.',
			detail: 'All via GitHub API in a Deno sandbox — no network access, no shell, whitelisted tools only.',
		},
		{
			Icon: RefreshCw,
			num: '04',
			title: 'Refine',
			description: 'Repeats up to 20 iterations until confident.',
			detail: 'Each loop narrows the analysis. Every finding must cite an exact line in the diff.',
		},
		{
			Icon: SendHorizonal,
			num: '05',
			title: 'Post Results',
			description: 'Findings posted as a PR comment. Check Run updated.',
			detail: 'P0/P1 findings block the merge. A rule-based reclassifier prevents the LLM from under-classifying critical issues.',
		},
	];

	let sectionEl: HTMLElement;
	let visible = false;

	onMount(() => {
		const observer = new IntersectionObserver(
			([entry]) => { if (entry.isIntersecting) visible = true; },
			{ threshold: 0.1 }
		);
		if (sectionEl) observer.observe(sectionEl);
		return () => observer.disconnect();
	});
</script>

<section id="how-it-works" class="hiw-section" bind:this={sectionEl}>
	<div class="section-wrap">
		<div class="section-header">
			<div class="section-eyebrow">How it works</div>
			<h2 class="section-title">The Recursive Reasoning Loop</h2>
			<p class="section-sub">Reason → Fetch → Refine → Repeat. Up to 20 iterations.</p>
		</div>

		<div class="steps-container" class:visible>
			{#each steps as step, i}
				<div class="step" style="--i: {i}">
					<div class="step-connector" class:last={i === steps.length - 1}>
						<div class="step-dot">
							<svelte:component this={step.Icon} size={14} />
						</div>
						<div class="step-line"></div>
					</div>
					<div class="step-content">
						<div class="step-num">{step.num}</div>
						<div class="step-body">
							<h3>{step.title}</h3>
							<p class="step-desc">{step.description}</p>
							<p class="step-detail">{step.detail}</p>
						</div>
					</div>
				</div>
			{/each}
		</div>
	</div>
</section>

<style>
	.hiw-section {
		padding: 6rem 0;
		background: var(--surface);
		border-top: 1px solid var(--border);
		border-bottom: 1px solid var(--border);
	}

	.section-header { text-align: center; margin-bottom: 4rem; }
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

	.steps-container {
		max-width: 700px; margin: 0 auto;
		display: flex; flex-direction: column; gap: 0;
	}

	.step {
		display: flex; gap: 1.5rem;
		opacity: 0; transform: translateX(-20px);
		transition: opacity 0.5s ease, transform 0.5s ease;
		transition-delay: calc(var(--i) * 120ms);
	}
	.steps-container.visible .step { opacity: 1; transform: translateX(0); }

	.step-connector {
		display: flex; flex-direction: column; align-items: center;
		flex-shrink: 0; width: 32px;
	}
	.step-dot {
		width: 32px; height: 32px; border-radius: 50%;
		background: var(--accent-glow);
		border: 1px solid rgba(124, 106, 247, 0.3);
		color: var(--accent);
		display: flex; align-items: center; justify-content: center;
		flex-shrink: 0;
	}
	.step-line {
		width: 1px; flex: 1; min-height: 32px;
		background: linear-gradient(to bottom, rgba(124,106,247,0.4), var(--border));
		margin-top: 4px;
	}
	.step-connector.last .step-line { display: none; }

	.step-content {
		display: flex; gap: 1rem; padding-bottom: 2.5rem; align-items: flex-start;
	}
	.step-num {
		font-size: 0.65rem; font-weight: 700; color: var(--accent);
		background: var(--accent-glow); border: 1px solid rgba(124,106,247,0.3);
		border-radius: 4px; padding: 0.2rem 0.35rem;
		font-family: monospace; flex-shrink: 0; margin-top: 6px;
	}
	.step-body h3 { font-size: 1rem; font-weight: 600; color: var(--text); margin-bottom: 0.3rem; }
	.step-desc { font-size: 0.875rem; color: var(--text); margin-bottom: 0.3rem; }
	.step-detail { font-size: 0.8rem; color: var(--muted); line-height: 1.6; }
</style>
