<script>
	import Editor from '$lib/Editor.svelte';
	import { importWebsite } from '$lib/api';

	// Two-step: fetch a draft from a URL, then hand it to the shared editor for
	// review-and-save. Nothing is persisted until the user confirms in the editor.
	let url = $state('');
	let busy = $state(false);
	let error = $state('');
	let draft = $state(/** @type {string | null} */ (null));

	async function fetchDraft() {
		busy = true;
		error = '';
		try {
			const result = await importWebsite(url.trim());
			draft = result.markdown;
		} catch (e) {
			error = String(e instanceof Error ? e.message : e);
		} finally {
			busy = false;
		}
	}
</script>

<p><a href="/">← All recipes</a></p>
<h1>Import from URL</h1>

{#if draft === null}
	<form
		onsubmit={(e) => {
			e.preventDefault();
			fetchDraft();
		}}
	>
		<label>
			Recipe URL
			<input
				bind:value={url}
				type="url"
				placeholder="https://…"
				required
				autocomplete="off"
			/>
		</label>
		<div class="actions">
			<button type="submit" disabled={busy || !url.trim()}>
				{busy ? 'Importing…' : 'Import'}
			</button>
			<a class="cancel" href="/new">Enter by hand instead</a>
		</div>
		{#if error}<p class="error">{error}</p>{/if}
	</form>
{:else}
	<p class="hint">Review the draft, fill any blanks, then save.</p>
	<Editor mode="create" initialMarkdown={draft} source="website" />
{/if}

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
	input {
		font-size: 1rem;
		padding: 0.5rem 0.6rem;
		border: 1px solid #d8cec6;
		border-radius: 8px;
		font-family: inherit;
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
	button:disabled {
		opacity: 0.6;
		cursor: default;
	}
	.cancel {
		color: #7a3b2e;
		text-decoration: none;
	}
	.hint {
		color: #9a8b80;
	}
	.error {
		color: #b23b2e;
	}
</style>
