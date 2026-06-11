<script>
	import { goto } from '$app/navigation';
	import { login } from '$lib/api';

	// Single-user login (Phase 4α). Only reachable/meaningful in hosted mode —
	// when auth is disabled the API never 401s, so nothing routes here.
	let password = $state('');
	let busy = $state(false);
	let error = $state('');

	async function submit() {
		busy = true;
		error = '';
		try {
			await login(password);
			goto('/');
		} catch (e) {
			error = String(e instanceof Error ? e.message : e);
		} finally {
			busy = false;
		}
	}
</script>

<div class="wrap">
	<h1>🍓 Recipe Box</h1>
	<form
		onsubmit={(e) => {
			e.preventDefault();
			submit();
		}}
	>
		<label>
			Password
			<!-- svelte-ignore a11y_autofocus -->
			<input type="password" bind:value={password} autocomplete="current-password" autofocus />
		</label>
		<button type="submit" disabled={busy || !password}>
			{busy ? 'Signing in…' : 'Sign in'}
		</button>
		{#if error}<p class="error">{error}</p>{/if}
	</form>
</div>

<style>
	.wrap {
		max-width: 22rem;
		margin: 4rem auto 0;
		display: grid;
		gap: 1rem;
		text-align: center;
	}
	form {
		display: grid;
		gap: 0.75rem;
		text-align: left;
	}
	label {
		display: grid;
		gap: 0.25rem;
		font-weight: 600;
	}
	input {
		font-size: 1rem;
		padding: 0.5rem 0.6rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		font-family: inherit;
	}
	button {
		padding: 0.55rem 1rem;
		border: 1px solid var(--accent);
		background: var(--accent);
		color: var(--on-accent);
		border-radius: 8px;
		cursor: pointer;
		font-size: 1rem;
	}
	button:disabled {
		opacity: 0.6;
		cursor: default;
	}
	.error {
		color: var(--danger);
	}
</style>
