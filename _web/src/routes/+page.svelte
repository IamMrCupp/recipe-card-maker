<script>
	import { onMount } from 'svelte';
	import { listRecipes, searchRecipes } from '$lib/api';

	let recipes = $state([]);
	let query = $state('');
	let loading = $state(true);
	let error = $state('');

	async function load() {
		loading = true;
		error = '';
		try {
			const q = query.trim();
			recipes = q ? await searchRecipes(q) : await listRecipes();
		} catch (e) {
			error = String(e);
		} finally {
			loading = false;
		}
	}

	function clear() {
		query = '';
		load();
	}

	onMount(load);
</script>

<div class="toolbar">
	<a class="new" href="/new">+ New recipe</a>
	<a class="new" href="/import">Import from URL</a>
	<a class="new" href="/import/photo">Import from photo</a>
	<a class="new" href="/import/social">Import from paste</a>
</div>

<form
	onsubmit={(e) => {
		e.preventDefault();
		load();
	}}
>
	<input placeholder="Search recipes…" bind:value={query} aria-label="Search recipes" />
	<button type="submit">Search</button>
	{#if query}<button type="button" onclick={clear}>Clear</button>{/if}
</form>

{#if loading}
	<p>Loading…</p>
{:else if error}
	<p class="error">Couldn’t load recipes: {error}</p>
{:else if recipes.length === 0}
	<p class="empty">No recipes found.</p>
{:else}
	<ul class="recipes">
		{#each recipes as r (r.id)}
			<li>
				<a href={`/recipes/${r.id}`}>
					<span class="title">{r.title}</span>
					{#if r.category}<span class="cat">{r.category}</span>{/if}
				</a>
				{#if r.tags?.length}
					<div class="tags">
						{#each r.tags as t}<span class="tag">{t}</span>{/each}
					</div>
				{/if}
			</li>
		{/each}
	</ul>
{/if}

<style>
	.toolbar {
		display: flex;
		justify-content: flex-end;
		margin-bottom: 0.75rem;
	}
	.new {
		text-decoration: none;
		font-weight: 600;
		color: var(--accent);
		border: 1px solid var(--accent);
		border-radius: 8px;
		padding: 0.4rem 0.8rem;
	}
	form {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 1rem;
	}
	input {
		flex: 1;
		padding: 0.5rem 0.65rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		font-size: 1rem;
	}
	button {
		padding: 0.5rem 0.9rem;
		border: 1px solid var(--accent);
		background: var(--accent);
		color: var(--on-accent);
		border-radius: 8px;
		cursor: pointer;
	}
	button[type='button'] {
		background: var(--surface);
		color: var(--accent);
	}
	.recipes {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 0.5rem;
	}
	.recipes li {
		background: var(--surface);
		border: 1px solid var(--rule);
		border-radius: 10px;
		padding: 0.75rem 0.9rem;
	}
	.recipes a {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		text-decoration: none;
		color: inherit;
	}
	.title {
		font-weight: 600;
	}
	.cat {
		font-size: 0.8rem;
		color: var(--muted);
	}
	.tags {
		margin-top: 0.4rem;
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
	}
	.tag {
		font-size: 0.72rem;
		background: var(--chip-bg);
		color: var(--chip-text);
		padding: 0.1rem 0.45rem;
		border-radius: 999px;
	}
	.error {
		color: var(--danger);
	}
	.empty {
		color: var(--muted);
	}
</style>
