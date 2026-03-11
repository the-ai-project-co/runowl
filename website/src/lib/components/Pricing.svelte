<script lang="ts">
	import { onMount } from 'svelte';

	const plans = [
		{
			name: 'Free',
			price: '$0',
			period: '/ forever',
			description: 'For individuals and open-source',
			cta: 'Get started',
			ctaLink: 'https://github.com/the-ai-project-co/RunOwl',
			featured: false,
			features: [
				{ text: 'AI code review (P0–P3)', included: true },
				{ text: 'Interactive Q&A', included: true },
				{ text: 'Surface security checks', included: true },
				{ text: 'GitHub webhook', included: true },
				{ text: 'CLI (npx runowl)', included: true },
				{ text: 'Deep OWASP analysis', included: false },
				{ text: 'SOLID analysis', included: false },
				{ text: 'GitHub Check Runs', included: false },
			]
		},
		{
			name: 'Team',
			price: '$29',
			period: '/ seat / mo',
			description: 'For engineering teams',
			cta: 'Start free trial',
			ctaLink: '#',
			featured: true,
			features: [
				{ text: 'Everything in Free', included: true },
				{ text: 'Full OWASP Top 10', included: true },
				{ text: 'SOLID / architecture', included: true },
				{ text: 'GitHub Check Runs', included: true },
				{ text: 'Race condition detection', included: true },
				{ text: 'Supply chain analysis', included: true },
				{ text: 'SSO / SAML', included: false },
				{ text: 'Self-hosted', included: false },
			]
		},
		{
			name: 'Business',
			price: '$79',
			period: '/ seat / mo',
			description: 'For larger teams',
			cta: 'Contact sales',
			ctaLink: 'mailto:hello@runowl.ai',
			featured: false,
			features: [
				{ text: 'Everything in Team', included: true },
				{ text: 'Priority support', included: true },
				{ text: 'SSO / SAML', included: true },
				{ text: 'Self-hosted', included: false },
				{ text: 'Audit logs', included: false },
			]
		},
		{
			name: 'Enterprise',
			price: 'Custom',
			period: '',
			description: 'For large organisations',
			cta: 'Contact us',
			ctaLink: 'mailto:hello@runowl.ai',
			featured: false,
			features: [
				{ text: 'Everything in Business', included: true },
				{ text: 'Self-hosted deployment', included: true },
				{ text: 'Audit logging', included: true },
				{ text: 'SCIM provisioning', included: true },
				{ text: 'SLA & dedicated support', included: true },
			]
		}
	];

	let cards: HTMLElement[] = [];
	let visible: boolean[] = new Array(plans.length).fill(false);

	onMount(() => {
		const observer = new IntersectionObserver(
			(entries) => {
				entries.forEach((entry) => {
					if (entry.isIntersecting) {
						const idx = cards.indexOf(entry.target as HTMLElement);
						if (idx !== -1) {
							setTimeout(() => {
								visible[idx] = true;
								visible = [...visible];
							}, idx * 80);
						}
					}
				});
			},
			{ threshold: 0.1 }
		);
		cards.forEach((card) => card && observer.observe(card));
		return () => observer.disconnect();
	});
</script>

<section id="pricing" class="pricing-section">
	<div class="section-wrap">
		<div class="section-header">
			<div class="section-eyebrow">Pricing</div>
			<h2 class="section-title">Simple, transparent pricing</h2>
			<p class="section-sub">Free for individuals and open-source. No credit card required.</p>
		</div>

		<div class="pricing-grid">
			{#each plans as plan, i}
				<div
					class="pricing-card"
					class:featured={plan.featured}
					class:visible={visible[i]}
					bind:this={cards[i]}
				>
					{#if plan.featured}
						<div class="featured-badge">Most popular</div>
					{/if}

					<div class="plan-header">
						<h3 class="plan-name">{plan.name}</h3>
						<p class="plan-desc">{plan.description}</p>
					</div>

					<div class="plan-price">
						<span class="price-amount">{plan.price}</span>
						{#if plan.period}
							<span class="price-period">{plan.period}</span>
						{/if}
					</div>

					<a href={plan.ctaLink} class="plan-cta" class:cta-featured={plan.featured}>
						{plan.cta}
					</a>

					<ul class="plan-features">
						{#each plan.features as feat}
							<li class:excluded={!feat.included}>
								<span class="feat-icon">{feat.included ? '✓' : '—'}</span>
								{feat.text}
							</li>
						{/each}
					</ul>
				</div>
			{/each}
		</div>
	</div>
</section>

<style>
	.pricing-section { padding: 6rem 0; }

	.section-header {
		text-align: center; margin-bottom: 3.5rem;
	}
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

	.pricing-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
		gap: 1.25rem;
		align-items: start;
	}

	.pricing-card {
		position: relative;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 1.75rem;
		opacity: 0; transform: translateY(20px);
		transition: opacity 0.5s ease, transform 0.5s ease, border-color 0.2s;
	}
	.pricing-card.visible { opacity: 1; transform: translateY(0); }
	.pricing-card.featured {
		border-color: var(--accent);
		box-shadow: 0 0 40px var(--accent-glow);
	}
	.pricing-card:not(.featured):hover { border-color: var(--muted); }

	.featured-badge {
		position: absolute; top: -12px; left: 50%; transform: translateX(-50%);
		background: var(--accent); color: #fff;
		font-size: 0.7rem; font-weight: 700;
		padding: 0.2rem 0.75rem; border-radius: 99px;
		white-space: nowrap;
	}

	.plan-header { margin-bottom: 1rem; }
	.plan-name { font-size: 1rem; font-weight: 700; color: var(--text); margin-bottom: 0.25rem; }
	.plan-desc { font-size: 0.8rem; color: var(--muted); }

	.plan-price {
		display: flex; align-items: baseline; gap: 0.35rem;
		margin-bottom: 1.25rem;
	}
	.price-amount { font-size: 2rem; font-weight: 800; color: var(--text); }
	.price-period { font-size: 0.8rem; color: var(--muted); }

	.plan-cta {
		display: block; text-align: center;
		padding: 0.6rem; border-radius: 8px;
		font-size: 0.875rem; font-weight: 600;
		background: var(--surface-2); color: var(--text);
		border: 1px solid var(--border);
		margin-bottom: 1.5rem;
		transition: all 0.2s;
	}
	.plan-cta:hover { border-color: var(--muted); }
	.plan-cta.cta-featured {
		background: var(--accent); color: #fff;
		border-color: var(--accent);
	}
	.plan-cta.cta-featured:hover { opacity: 0.9; }

	.plan-features {
		list-style: none;
		display: flex; flex-direction: column; gap: 0.5rem;
		font-size: 0.84rem;
	}
	.plan-features li {
		display: flex; align-items: center; gap: 0.6rem;
		color: var(--text);
	}
	.plan-features li.excluded { color: var(--muted); opacity: 0.5; }
	.feat-icon { color: var(--green); font-size: 0.8rem; width: 14px; flex-shrink: 0; }
	li.excluded .feat-icon { color: var(--muted); }
</style>
