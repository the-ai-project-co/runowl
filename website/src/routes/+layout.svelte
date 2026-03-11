<script lang="ts">
	import '../app.css';

	let { children } = $props();
</script>

<svelte:head>
	<title>RunOwl — AI Code Review That Actually Reads Your Code</title>
	<meta name="description" content="Open-source AI agent that reviews GitHub PRs, finds bugs and security issues, and posts findings as PR comments. Free tier + paid deep analysis." />
	<meta property="og:title" content="RunOwl — AI Code Review" />
	<meta property="og:description" content="One agent. Reviews, tests, ships." />
	<meta property="og:type" content="website" />
	<meta property="og:url" content="https://runowl.ai" />
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
	<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
</svelte:head>

{@render children()}
