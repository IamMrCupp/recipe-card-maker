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
	form {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 1rem;
	}
	input {
		flex: 1;
		padding: 0.5rem 0.65rem;
		border: 1px solid #d8cec6;
		border-radius: 8px;
		font-size: 1rem;
	}
	button {
		padding: 0.5rem 0.9rem;
		border: 1px solid #7a3b2e;
		background: #7a3b2e;
		color: #fff;
		border-radius: 8px;
		cursor: pointer;
	}
	button[type='button'] {
		background: #fff;
		color: #7a3b2e;
	}
	.recipes {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 0.5rem;
	}
	.recipes li {
		background: #fff;
		border: 1px solid #ece4dd;
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
		color: #9a8b80;
	}
	.tags {
		margin-top: 0.4rem;
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
	}
	.tag {
		font-size: 0.72rem;
		background: #f1e9e2;
		color: #6b5347;
		padding: 0.1rem 0.45rem;
		border-radius: 999px;
	}
	.error {
		color: #b23b2e;
	}
	.empty {
		color: #9a8b80;
	}
</style>
