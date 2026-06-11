<script>
	import '../app.css';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import favicon from '$lib/assets/favicon.svg';
	import { authStatus, logout } from '$lib/api';

	let { children } = $props();

	// Theme: 'auto' (follow OS), 'light', or 'dark'. The no-flash script in app.html
	// applies an explicit saved choice before paint; here we sync the label and cycle.
	let theme = $state('auto');
	const labels = { auto: '🌗 Auto', light: '☀️ Light', dark: '🌙 Dark' };

	// Hosted mode (Phase 4α): show a logout control when actually signed in.
	// In local/dev mode auth_enabled is false and the control stays hidden.
	let authedSession = $state(false);

	onMount(() => {
		theme = localStorage.getItem('theme') || 'auto';
		authStatus()
			.then((s) => {
				authedSession = s.auth_enabled && s.authenticated;
			})
			.catch(() => {});
	});

	async function signOut() {
		try {
			await logout();
		} catch {
			/* cookie may already be gone */
		}
		authedSession = false;
		goto('/login');
	}

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
	<div class="controls">
		<button class="theme" onclick={cycle} title="Toggle light / dark / auto">{labels[theme]}</button>
		{#if authedSession}
			<button class="theme" onclick={signOut} title="Sign out">Sign out</button>
		{/if}
	</div>
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
	.controls {
		display: flex;
		gap: 0.4rem;
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
