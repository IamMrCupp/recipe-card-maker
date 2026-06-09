<script>
	import { page } from '$app/state';
	import { getRecipe } from '$lib/api';
	import Editor from '$lib/Editor.svelte';

	let recipe = $state(null);
	let error = $state('');

	$effect(() => {
		const id = page.params.id;
		recipe = null;
		error = '';
		getRecipe(id)
			.then((r) => {
				recipe = r;
			})
			.catch((e) => {
				error = String(e instanceof Error ? e.message : e);
			});
	});
</script>

{#if error}
	<p class="error">Couldn’t load recipe: {error}</p>
{:else if recipe}
	<p><a href={`/recipes/${recipe.id}`}>← Back to recipe</a></p>
	<h1>Edit recipe</h1>
	<Editor
		mode="edit"
		id={recipe.id}
		initialMarkdown={recipe.markdown}
		initialImages={recipe.images}
	/>
{:else}
	<p>Loading…</p>
{/if}

<style>
	.error {
		color: var(--danger);
	}
</style>
