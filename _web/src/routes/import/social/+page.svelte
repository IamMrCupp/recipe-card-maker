<script>
	import { onMount } from 'svelte';
	import Editor from '$lib/Editor.svelte';
	import { importSocial, importCapabilities } from '$lib/api';

	// Paste a caption/post → extract a draft → hand to the shared editor.
	// Paste-only and LLM-only, so we gate the form on capabilities.
	let available = $state(/** @type {boolean | null} */ (null)); // null = checking
	let text = $state('');
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

	async function extract() {
		if (!text.trim()) return;
		busy = true;
		error = '';
		try {
			const result = await importSocial(text);
			draft = result.markdown;
		} catch (e) {
			error = String(e instanceof Error ? e.message : e);
		} finally {
			busy = false;
		}
	}
</script>

<p><a href="/">← All recipes</a></p>
<h1>Import from paste</h1>

{#if draft !== null}
	<p class="hint">Review the draft, fill any blanks, then save.</p>
	<Editor mode="create" initialMarkdown={draft} source="social" />
{:else if available === false}
	<p class="hint">
		AI import isn't configured on this server. <a href="/new">Enter by hand</a> instead.
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
			Pasted recipe text
			<textarea bind:value={text} rows="12" placeholder="Paste the caption or post text…"></textarea>
		</label>
		<div class="actions">
			<button type="submit" disabled={busy || !text.trim()}>
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
	textarea {
		font-size: 1rem;
		padding: 0.5rem 0.6rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		font-family: inherit;
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
