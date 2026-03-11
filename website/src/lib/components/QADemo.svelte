<script lang="ts">
	import { onMount } from 'svelte';
	import { CircleUser, Bot, Check, Terminal } from 'lucide-svelte';

	const conversation = [
		{ role: 'user', text: 'Are there any race conditions in the worker pool changes?', citations: [] },
		{ role: 'assistant', text: "Yes — there's a TOCTOU issue in the new `claim_job()` method.", citations: ['src/workers/pool.py:83'] },
		{ role: 'assistant', text: 'The check `if job.status == "pending"` and the subsequent UPDATE are not atomic. Two workers can claim the same job simultaneously.', citations: ['src/workers/pool.py:83–91'] },
		{ role: 'user', text: 'How would you fix it?', citations: [] },
		{ role: 'assistant', text: "Use `UPDATE ... WHERE status = 'pending' RETURNING id` — a single atomic operation. The row is claimed only if the status matches at the moment of update.", citations: [] },
	];

	let visible: boolean[] = new Array(conversation.length).fill(false);
	let sectionEl: HTMLElement;
	let started = false;

	function playConversation() {
		if (started) return;
		started = true;
		conversation.forEach((_, i) => {
			setTimeout(() => { visible[i] = true; visible = [...visible]; }, i * 650);
		});
	}

	onMount(() => {
		const observer = new IntersectionObserver(
			([entry]) => { if (entry.isIntersecting) playConversation(); },
			{ threshold: 0.3 }
		);
		if (sectionEl) observer.observe(sectionEl);
		return () => observer.disconnect();
	});
</script>

<section class="qa-section" bind:this={sectionEl}>
	<div class="section-wrap">
		<div class="qa-layout">
			<div class="qa-copy">
				<div class="section-eyebrow">Interactive Q&A</div>
				<h2 class="section-title">Ask anything about the PR</h2>
				<p class="section-sub">
					After the review, ask follow-up questions in natural language.
					RunOwl answers with citations to the exact lines in the diff.
				</p>
				<ul class="qa-features">
					<li><Check size={14} class="check-icon" /><span>Race condition and concurrency queries</span></li>
					<li><Check size={14} class="check-icon" /><span>Security-focused deep dives</span></li>
					<li><Check size={14} class="check-icon" /><span>Architecture and design questions</span></li>
					<li><Check size={14} class="check-icon" /><span>Remediation suggestions with code context</span></li>
				</ul>
				<div class="qa-command">
					<Terminal size={13} class="cmd-icon" />
					<code>npx runowl ask --url &lt;pr-url&gt;</code>
				</div>
			</div>

			<div class="qa-chat">
				<div class="chat-header">
					<div class="chat-dots">
						<span class="dot r"></span><span class="dot y"></span><span class="dot g"></span>
					</div>
					<span class="chat-title">RunOwl Q&A</span>
				</div>
				<div class="chat-body">
					{#each conversation as msg, i}
						{#if visible[i]}
							<div class="msg msg-{msg.role}">
								{#if msg.role === 'user'}
									<div class="msg-label">
										<CircleUser size={12} />
										You
									</div>
								{:else}
									<div class="msg-label owl">
										<Bot size={12} />
										RunOwl
									</div>
								{/if}
								<div class="msg-bubble">
									{msg.text}
									{#if msg.citations.length > 0}
										<div class="citations">
											{#each msg.citations as cite}
												<span class="cite">{cite}</span>
											{/each}
										</div>
									{/if}
								</div>
							</div>
						{/if}
					{/each}
				</div>
			</div>
		</div>
	</div>
</section>

<style>
	.qa-section { padding: 6rem 0; }

	.qa-layout {
		display: grid; grid-template-columns: 1fr 1fr;
		gap: 4rem; align-items: center;
	}
	@media (max-width: 768px) { .qa-layout { grid-template-columns: 1fr; gap: 2rem; } }

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
	.section-sub { font-size: 0.95rem; color: var(--muted); line-height: 1.7; margin-bottom: 1.75rem; }

	.qa-features {
		list-style: none; display: flex; flex-direction: column; gap: 0.6rem;
		margin-bottom: 1.75rem;
	}
	.qa-features li {
		display: flex; align-items: center; gap: 0.6rem;
		font-size: 0.9rem; color: var(--text);
	}
	:global(.check-icon) { color: var(--green); flex-shrink: 0; }

	.qa-command {
		display: inline-flex; align-items: center; gap: 0.5rem;
		background: var(--surface); border: 1px solid var(--border);
		border-radius: 8px; padding: 0.6rem 1rem;
	}
	:global(.cmd-icon) { color: var(--muted); }
	.qa-command code {
		font-family: monospace; font-size: 0.82rem; color: var(--green);
	}

	.qa-chat {
		background: var(--surface); border: 1px solid var(--border);
		border-radius: 12px; overflow: hidden;
		box-shadow: 0 20px 60px rgba(0,0,0,0.3);
	}
	.chat-header {
		background: var(--surface-2); border-bottom: 1px solid var(--border);
		padding: 0.75rem 1rem;
		display: flex; align-items: center; gap: 0.75rem;
	}
	.chat-dots { display: flex; gap: 6px; }
	.dot { width: 10px; height: 10px; border-radius: 50%; }
	.dot.r { background: #ff5f57; }
	.dot.y { background: #febc2e; }
	.dot.g { background: #28c840; }
	.chat-title { font-size: 0.8rem; color: var(--muted); flex: 1; text-align: center; }

	.chat-body {
		padding: 1.25rem; display: flex; flex-direction: column; gap: 1rem;
		min-height: 340px; font-size: 0.84rem;
	}

	.msg { animation: msgIn 0.35s ease forwards; }
	@keyframes msgIn { to { opacity: 1; transform: translateY(0); } }
	.msg { opacity: 0; transform: translateY(8px); }

	.msg-label {
		font-size: 0.7rem; font-weight: 600; color: var(--muted);
		margin-bottom: 0.3rem; text-transform: uppercase;
		letter-spacing: 0.06em;
		display: flex; align-items: center; gap: 0.35rem;
	}
	.msg-label.owl { color: var(--accent); }

	.msg-bubble {
		padding: 0.75rem 1rem; border-radius: 8px;
		line-height: 1.6; color: var(--text);
	}
	.msg-user .msg-bubble {
		background: var(--accent-glow);
		border: 1px solid rgba(124,106,247,0.2);
		margin-left: 1.5rem;
	}
	.msg-assistant .msg-bubble {
		background: var(--surface-2); border: 1px solid var(--border);
	}

	.citations { margin-top: 0.5rem; display: flex; flex-wrap: wrap; gap: 0.4rem; }
	.cite {
		font-family: monospace; font-size: 0.72rem;
		background: var(--bg); color: var(--accent-2);
		padding: 0.1rem 0.4rem; border-radius: 4px;
		border: 1px solid var(--border);
	}
</style>
