<script>
	import { goto } from '$app/navigation';
	import { createRecipe, updateRecipe, deleteRecipe, attachImage, deleteImage } from '$lib/api';

	// The shared review-and-save surface. Importers (§3.D) reuse this by passing a
	// pre-filled `initialMarkdown` draft plus a provenance `source` (website/photo/
	// social); hand entry passes a starter and the default 'hand' source.
	let {
		mode = 'create',
		id = null,
		initialMarkdown = '',
		initialCategory = '',
		initialImages = [],
		source = 'hand'
	} = $props();

	let markdown = $state(initialMarkdown);
	let category = $state(initialCategory);
	let images = $state(initialImages); // servable URLs; managed in edit mode (§3.E.1)
	let imgError = $state('');
	let busy = $state(false);
	let error = $state('');

	async function onAttach(e) {
		const input = e.target;
		const file = input.files?.[0];
		if (!file) return;
		imgError = '';
		try {
			const updated = await attachImage(id, file);
			images = updated.images;
		} catch (err) {
			imgError = String(err instanceof Error ? err.message : err);
		}
		input.value = ''; // allow re-selecting the same file
	}

	async function onRemove(url) {
		imgError = '';
		const ref = url.split('/').pop();
		try {
			await deleteImage(id, ref);
			images = images.filter((u) => u !== url);
		} catch (err) {
			imgError = String(err instanceof Error ? err.message : err);
		}
	}

	async function save() {
		busy = true;
		error = '';
		try {
			const recipe =
				mode === 'create'
					? await createRecipe(markdown, { category: category.trim() || undefined, source })
					: await updateRecipe(id, markdown);
			goto(`/recipes/${recipe.id}`);
		} catch (e) {
			error = String(e instanceof Error ? e.message : e);
			busy = false;
		}
	}

	async function remove() {
		if (!confirm('Delete this recipe? This cannot be undone.')) return;
		busy = true;
		error = '';
		try {
			await deleteRecipe(id);
			goto('/');
		} catch (e) {
			error = String(e instanceof Error ? e.message : e);
			busy = false;
		}
	}
</script>

<form
	onsubmit={(e) => {
		e.preventDefault();
		save();
	}}
>
	{#if mode === 'create'}
		<label>
			Category <small>(folder; optional — also read from frontmatter)</small>
			<input bind:value={category} placeholder="e.g. cakes" />
		</label>
	{/if}

	<label>
		Recipe (markdown)
		<textarea bind:value={markdown} rows="22" spellcheck="false"></textarea>
	</label>

	{#if mode === 'edit'}
		<div class="images">
			<span class="images-label">Images</span>
			<div class="thumbs">
				{#each images as url (url)}
					<div class="thumb">
						<img src={url} alt="recipe" loading="lazy" />
						<button type="button" class="remove" onclick={() => onRemove(url)}>Remove</button>
					</div>
				{/each}
			</div>
			<input type="file" accept="image/*" onchange={onAttach} />
			{#if imgError}<p class="error">{imgError}</p>{/if}
		</div>
	{/if}

	{#if error}<p class="error">{error}</p>{/if}

	<div class="actions">
		<button type="submit" disabled={busy}>{mode === 'create' ? 'Create' : 'Save'}</button>
		{#if mode === 'edit'}
			<button type="button" class="danger" onclick={remove} disabled={busy}>Delete</button>
		{/if}
		<a class="cancel" href={mode === 'edit' && id ? `/recipes/${id}` : '/'}>Cancel</a>
	</div>
</form>

<style>
	form {
		display: grid;
		gap: 0.75rem;
	}
	label {
		display: grid;
		gap: 0.25rem;
		font-weight: 600;
	}
	small {
		font-weight: 400;
		color: #9a8b80;
	}
	input,
	textarea {
		font-size: 1rem;
		padding: 0.5rem 0.6rem;
		border: 1px solid #d8cec6;
		border-radius: 8px;
		font-family: inherit;
	}
	textarea {
		font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
		font-size: 0.9rem;
		line-height: 1.45;
		resize: vertical;
	}
	.actions {
		display: flex;
		align-items: center;
		gap: 0.6rem;
	}
	button {
		padding: 0.5rem 1rem;
		border: 1px solid #7a3b2e;
		background: #7a3b2e;
		color: #fff;
		border-radius: 8px;
		cursor: pointer;
	}
	button.danger {
		background: #fff;
		color: #b23b2e;
		border-color: #d8b0aa;
	}
	.cancel {
		color: #7a3b2e;
		text-decoration: none;
	}
	.images {
		display: grid;
		gap: 0.4rem;
	}
	.images-label {
		font-weight: 600;
	}
	.thumbs {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}
	.thumb {
		display: grid;
		gap: 0.2rem;
		justify-items: center;
	}
	.thumb img {
		width: 7rem;
		height: 7rem;
		object-fit: cover;
		border-radius: 8px;
		border: 1px solid #d8cec6;
	}
	.thumb .remove {
		padding: 0.2rem 0.5rem;
		font-size: 0.75rem;
		background: #fff;
		color: #b23b2e;
		border-color: #d8b0aa;
	}
	.error {
		color: #b23b2e;
	}
</style>
