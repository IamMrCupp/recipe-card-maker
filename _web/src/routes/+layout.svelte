<script>
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<link rel="manifest" href="/manifest.webmanifest" />
	<meta name="theme-color" content="#7a3b2e" />
</svelte:head>

<header>
	<a class="brand" href="/">🍓 Recipe Box</a>
</header>

<main>
	{@render children()}
</main>

<style>
	:global(body) {
		margin: 0;
		font-family:
			-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
		color: #2b2b2b;
		background: #faf7f4;
	}
	header {
		padding: 0.75rem 1rem;
		border-bottom: 1px solid #e7ded7;
		background: #fff;
		position: sticky;
		top: 0;
	}
	.brand {
		font-weight: 700;
		font-size: 1.15rem;
		text-decoration: none;
		color: #7a3b2e;
	}
	main {
		max-width: 760px;
		margin: 0 auto;
		padding: 1rem;
	}
</style>
