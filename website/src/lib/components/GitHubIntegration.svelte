<script lang="ts">
	import { onMount } from 'svelte';
	import { XCircle, CircleCheck, Webhook, ScanSearch, FileText, CheckCheck } from 'lucide-svelte';

	let sectionEl: HTMLElement;
	let visible = false;

	onMount(() => {
		const observer = new IntersectionObserver(
			([entry]) => { if (entry.isIntersecting) visible = true; },
			{ threshold: 0.2 }
		);
		if (sectionEl) observer.observe(sectionEl);
		return () => observer.disconnect();
	});

	const ghSteps = [
		{ Icon: Webhook,      title: 'PR opens',          desc: 'GitHub sends a webhook to RunOwl' },
		{ Icon: ScanSearch,   title: 'Check Run created', desc: 'Status shows "in progress" on the PR' },
		{ Icon: FileText,     title: 'Review runs',       desc: 'RLM loop analyses the diff and context' },
		{ Icon: CheckCheck,   title: 'Results posted',    desc: 'Comment + Check Run pass/fail' },
	];
</script>

<section class="gh-section" bind:this={sectionEl}>
	<div class="section-wrap">
		<div class="gh-layout" class:visible>
			<!-- PR comment mockup -->
			<div class="gh-mockup">
				<div class="pr-comment">
					<div class="comment-header">
						<div class="avatar">
							<svg width="16" height="16" viewBox="0 0 28 28" fill="none">
								<circle cx="14" cy="14" r="13" stroke="var(--accent)" stroke-width="1.5"/>
								<circle cx="14" cy="14" r="5" fill="var(--accent)"/>
							</svg>
						</div>
						<div class="comment-meta">
							<span class="bot-name">runowl</span>
							<span class="bot-badge">bot</span>
							<span class="comment-time">just now</span>
						</div>
						<div class="check-pill fail">
							<XCircle size={12} />
							2 blocking findings
						</div>
					</div>
					<div class="comment-body">
						<div class="finding-row p0">
							<span class="sev">P0</span>
							<div class="finding-text">
								<span class="file-ref">src/auth.py:47</span>
								<p>Hardcoded JWT secret <code>secret="my-app-secret"</code> is exposed in source. Rotate immediately and use environment variables.</p>
							</div>
						</div>
						<div class="finding-row p1">
							<span class="sev p1">P1</span>
							<div class="finding-text">
								<span class="file-ref">src/routes.py:103</span>
								<p>New <code>/admin/users</code> endpoint has no authentication decorator.</p>
							</div>
						</div>
						<div class="finding-row p2">
							<span class="sev p2">P2</span>
							<div class="finding-text">
								<span class="file-ref">src/db.py:29</span>
								<p>SQL query uses string concatenation with user input.</p>
							</div>
						</div>
					</div>
				</div>

				<div class="check-run-block fail">
					<XCircle size={16} color="var(--red)" />
					<div class="check-run-text">
						<strong>RunOwl Code Review</strong>
						<span>2 blocking findings — merge blocked</span>
					</div>
					<span class="check-details">Details</span>
				</div>
			</div>

			<!-- Right copy -->
			<div class="gh-copy">
				<div class="section-eyebrow">GitHub Integration</div>
				<h2 class="section-title">Seamless PR workflow</h2>
				<p class="section-sub">
					Install the GitHub App once. Every PR triggers a review automatically —
					no CLI, no setup per repo.
				</p>
				<div class="gh-steps">
					{#each ghSteps as step, i}
						<div class="gh-step">
							<div class="step-circle">
								<svelte:component this={step.Icon} size={14} />
							</div>
							<div>
								<strong>{step.title}</strong>
								<p>{step.desc}</p>
							</div>
						</div>
					{/each}
				</div>
			</div>
		</div>
	</div>
</section>

<style>
	.gh-section {
		padding: 6rem 0;
		background: var(--surface);
		border-top: 1px solid var(--border);
		border-bottom: 1px solid var(--border);
	}

	.gh-layout {
		display: grid; grid-template-columns: 1fr 1fr;
		gap: 4rem; align-items: center;
		opacity: 0; transform: translateY(20px);
		transition: opacity 0.6s ease, transform 0.6s ease;
	}
	.gh-layout.visible { opacity: 1; transform: translateY(0); }
	@media (max-width: 768px) { .gh-layout { grid-template-columns: 1fr; } }

	.section-eyebrow {
		font-size: 0.75rem; font-weight: 700;
		letter-spacing: 0.12em; text-transform: uppercase;
		color: var(--accent); margin-bottom: 0.75rem;
	}
	.section-title {
		font-size: clamp(1.5rem, 3vw, 2.25rem);
		font-weight: 800; letter-spacing: -0.02em;
		margin-bottom: 0.75rem; color: var(--text);
	}
	.section-sub { font-size: 0.95rem; color: var(--muted); line-height: 1.7; margin-bottom: 2rem; }

	.pr-comment {
		background: var(--bg); border: 1px solid var(--border);
		border-radius: 8px; overflow: hidden; margin-bottom: 0.75rem;
		font-size: 0.82rem;
	}
	.comment-header {
		display: flex; align-items: center; gap: 0.6rem;
		padding: 0.75rem 1rem;
		background: var(--surface-2); border-bottom: 1px solid var(--border);
	}
	.avatar {
		width: 28px; height: 28px; border-radius: 50%;
		background: var(--accent-glow);
		display: flex; align-items: center; justify-content: center; flex-shrink: 0;
	}
	.bot-name { font-weight: 600; color: var(--text); }
	.bot-badge {
		font-size: 0.65rem; padding: 0.1rem 0.35rem;
		border: 1px solid var(--border); border-radius: 4px; color: var(--muted);
	}
	.comment-time { color: var(--muted); margin-left: auto; }
	.check-pill {
		display: flex; align-items: center; gap: 0.3rem;
		font-size: 0.72rem; padding: 0.2rem 0.5rem;
		border-radius: 4px; font-weight: 600;
	}
	.check-pill.fail { background: rgba(248,113,113,0.15); color: var(--red); }

	.comment-body { padding: 0.75rem 1rem; display: flex; flex-direction: column; gap: 0.75rem; }

	.finding-row {
		display: flex; gap: 0.75rem; align-items: flex-start;
		padding: 0.6rem; border-radius: 6px;
		background: rgba(248,113,113,0.05); border: 1px solid rgba(248,113,113,0.15);
	}
	.finding-row.p1 { background: rgba(251,191,36,0.05); border-color: rgba(251,191,36,0.15); }
	.finding-row.p2 { background: rgba(107,114,128,0.05); border-color: rgba(107,114,128,0.15); }

	.sev {
		font-size: 0.65rem; font-weight: 700;
		padding: 0.15rem 0.35rem; border-radius: 3px;
		background: var(--red); color: #fff; flex-shrink: 0; margin-top: 2px;
	}
	.sev.p1 { background: var(--yellow); color: #000; }
	.sev.p2 { background: var(--muted); }

	.file-ref {
		font-family: monospace; font-size: 0.72rem;
		color: var(--accent-2); display: block; margin-bottom: 0.2rem;
	}
	.finding-text p { color: var(--muted); line-height: 1.5; }
	.finding-text code {
		background: var(--surface); padding: 0.1rem 0.3rem;
		border-radius: 3px; font-size: 0.75rem; color: var(--text);
	}

	.check-run-block {
		display: flex; align-items: center; gap: 0.75rem;
		background: var(--bg); border: 1px solid rgba(248,113,113,0.3);
		border-radius: 8px; padding: 0.75rem 1rem; font-size: 0.82rem;
	}
	.check-run-text { flex: 1; }
	.check-run-text strong { display: block; color: var(--text); }
	.check-run-text span { color: var(--muted); font-size: 0.78rem; }
	.check-details { color: var(--accent); font-size: 0.78rem; }

	.gh-steps { display: flex; flex-direction: column; gap: 1.25rem; }
	.gh-step { display: flex; align-items: flex-start; gap: 1rem; font-size: 0.875rem; }
	.step-circle {
		width: 32px; height: 32px; border-radius: 50%;
		background: var(--accent-glow); border: 1px solid rgba(124,106,247,0.3);
		color: var(--accent);
		display: flex; align-items: center; justify-content: center; flex-shrink: 0;
	}
	.gh-step strong { display: block; color: var(--text); margin-bottom: 0.15rem; }
	.gh-step p { color: var(--muted); }
</style>
