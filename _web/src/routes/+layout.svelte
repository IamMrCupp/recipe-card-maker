<script>
	import '../app.css';
	import { onMount } from 'svelte';
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();

	// Theme: 'auto' (follow OS), 'light', or 'dark'. The no-flash script in app.html
	// applies an explicit saved choice before paint; here we sync the label and cycle.
	let theme = $state('auto');
	const labels = { auto: '🌗 Auto', light: '☀️ Light', dark: '🌙 Dark' };

	onMount(() => {
		theme = localStorage.getItem('theme') || 'auto';
	});

	function cycle() {
		theme = theme === 'auto' ? 'light' : theme === 'light' ? 'dark' : 'auto';
		if (theme === 'auto') {
			delete document.documentElement.dataset.theme; // fall back to OS preference
			localStorage.removeItem('theme');
		} else {
			document.documentElement.dataset.theme = theme;
			localStorage.setItem('theme', theme);
		}
	}
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<link rel="manifest" href="/manifest.webmanifest" />
	<meta name="theme-color" content="#7a3b2e" />
</svelte:head>

<header>
	<a class="brand" href="/">🍓 Recipe Box</a>
	<button class="theme" onclick={cycle} title="Toggle light / dark / auto">{labels[theme]}</button>
</header>

<main>
	{@render children()}
</main>

<style>
	:global(body) {
		margin: 0;
		font-family:
			-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
		color: var(--text);
		background: var(--bg);
	}
	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		padding: 0.75rem 1rem;
		border-bottom: 1px solid var(--border);
		background: var(--surface);
		position: sticky;
		top: 0;
	}
	.brand {
		font-weight: 700;
		font-size: 1.15rem;
		text-decoration: none;
		color: var(--accent);
	}
	.theme {
		font: inherit;
		font-size: 0.8rem;
		padding: 0.25rem 0.6rem;
		border: 1px solid var(--border);
		border-radius: 999px;
		background: var(--bg);
		color: var(--text-muted);
		cursor: pointer;
	}
	main {
		max-width: 760px;
		margin: 0 auto;
		padding: 1rem;
	}
</style>
