<script>
	import { onMount } from 'svelte';
	import Editor from '$lib/Editor.svelte';
	import { importPhoto, importCapabilities } from '$lib/api';

	// Capture or upload a photo → extract a draft → hand to the shared editor.
	// Photo import is LLM-only, so we gate the form on capabilities.
	let available = $state(/** @type {boolean | null} */ (null)); // null = checking
	let file = $state(/** @type {File | null} */ (null));
	let busy = $state(false);
	let error = $state('');
	let draft = $state(/** @type {string | null} */ (null));

	onMount(async () => {
		try {
			const caps = await importCapabilities();
			available = caps.llm_extraction;
		} catch {
			available = false;
		}
	});

	/** @param {Event} e */
	function pick(e) {
		const input = /** @type {HTMLInputElement} */ (e.target);
		file = input.files?.[0] ?? null;
		error = '';
	}

	async function extract() {
		if (!file) return;
		busy = true;
		error = '';
		try {
			const result = await importPhoto(file);
			draft = result.markdown;
		} catch (e) {
			error = String(e instanceof Error ? e.message : e);
		} finally {
			busy = false;
		}
	}
</script>

<p><a href="/">← All recipes</a></p>
<h1>Import from photo</h1>

{#if draft !== null}
	<p class="hint">Review the draft, fill any blanks, then save. The photo will be attached.</p>
	<Editor mode="create" initialMarkdown={draft} source="photo" pendingImage={file} />
{:else if available === false}
	<p class="hint">
		AI photo import isn't configured on this server. <a href="/new">Enter by hand</a> instead.
	</p>
{:else if available === null}
	<p class="hint">Checking…</p>
{:else}
	<form
		onsubmit={(e) => {
			e.preventDefault();
			extract();
		}}
	>
		<label>
			Photo
			<input type="file" accept="image/*" capture="environment" onchange={pick} />
		</label>
		<div class="actions">
			<button type="submit" disabled={busy || !file}>
				{busy ? 'Reading…' : 'Extract'}
			</button>
			<a class="cancel" href="/new">Enter by hand instead</a>
		</div>
		{#if error}<p class="error">{error}</p>{/if}
	</form>
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
	}
	.actions {
		display: flex;
		align-items: center;
		gap: 0.6rem;
	}
	button {
		padding: 0.5rem 1rem;
		border: 1px solid var(--accent);
		background: var(--accent);
		color: var(--on-accent);
		border-radius: 8px;
		cursor: pointer;
	}
	button:disabled {
		opacity: 0.6;
		cursor: default;
	}
	.cancel {
		color: var(--accent);
		text-decoration: none;
	}
	.hint {
		color: var(--muted);
	}
	.error {
		color: var(--danger);
	}
</style>
