<script>
	import { page } from '$app/state';
	import { getRecipe } from '$lib/api';

	let recipe = $state(null);
	let loading = $state(true);
	let error = $state('');

	$effect(() => {
		const id = page.params.id;
		loading = true;
		error = '';
		recipe = null;
		getRecipe(id)
			.then((r) => {
				recipe = r;
			})
			.catch((e) => {
				error = String(e);
			})
			.finally(() => {
				loading = false;
			});
	});
</script>

<p><a href="/">← All recipes</a></p>

{#if loading}
	<p>Loading…</p>
{:else if error}
	<p class="error">Couldn’t load recipe: {error}</p>
{:else if recipe}
	<article>
		<h1>{recipe.title}</h1>
		{#if recipe.category}<p class="cat">{recipe.category}</p>{/if}
		{#if recipe.tags?.length}
			<div class="tags">
				{#each recipe.tags as t}<span class="tag">{t}</span>{/each}
			</div>
		{/if}

		<div class="downloads">
			<a href={`/api/recipes/${recipe.id}/card.pdf`} target="_blank" rel="noopener">
				⬇ 4×6 card
			</a>
			<a href={`/api/recipes/${recipe.id}/letter.pdf`} target="_blank" rel="noopener">
				⬇ Letter page
			</a>
		</div>

		{#if recipe.intro}<p class="intro">{recipe.intro}</p>{/if}

		{#each recipe.sections as section (section.name)}
			<section>
				<h2>{section.name}</h2>
				{#if section.intro}<p>{section.intro}</p>{/if}
				{#each Object.entries(section.blocks) as [name, items] (name)}
					<h3>{name}</h3>
					<ul>
						{#each items as item}<li>{item}</li>{/each}
					</ul>
				{/each}
				{#each section.prose as para}<p>{para}</p>{/each}
			</section>
		{/each}
	</article>
{/if}

<style>
	.cat {
		color: #9a8b80;
		margin: 0.2rem 0;
	}
	.tags {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
		margin-bottom: 0.5rem;
	}
	.tag {
		font-size: 0.72rem;
		background: #f1e9e2;
		color: #6b5347;
		padding: 0.1rem 0.45rem;
		border-radius: 999px;
	}
	.downloads {
		display: flex;
		gap: 0.5rem;
		margin: 0.75rem 0;
	}
	.downloads a {
		font-size: 0.85rem;
		text-decoration: none;
		color: #7a3b2e;
		border: 1px solid #d8cec6;
		border-radius: 8px;
		padding: 0.3rem 0.6rem;
	}
	.intro {
		font-style: italic;
		color: #5b5048;
	}
	h2 {
		border-bottom: 1px solid #ece4dd;
		padding-bottom: 0.2rem;
		margin-top: 1.5rem;
	}
	h3 {
		margin-bottom: 0.3rem;
		color: #7a3b2e;
	}
	.error {
		color: #b23b2e;
	}
</style>
