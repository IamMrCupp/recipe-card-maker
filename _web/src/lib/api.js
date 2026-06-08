// Thin client for the FastAPI JSON API (served same-origin under /api).

/** @param {string} path */
async function get(path) {
	const res = await fetch(`/api${path}`);
	if (!res.ok) {
		throw new Error(`${res.status} ${res.statusText}`);
	}
	return res.json();
}

/**
 * @param {string} method
 * @param {string} path
 * @param {unknown} [body]
 */
async function send(method, path, body) {
	const res = await fetch(`/api${path}`, {
		method,
		headers: { 'content-type': 'application/json' },
		body: body === undefined ? undefined : JSON.stringify(body)
	});
	if (!res.ok) {
		let detail = `${res.status} ${res.statusText}`;
		try {
			const data = await res.json();
			if (data?.detail) detail = data.detail;
		} catch {
			/* non-JSON error body */
		}
		throw new Error(detail);
	}
	return res.status === 204 ? null : res.json();
}

/**
 * List recipes, optionally filtered.
 * @param {{ category?: string, tag?: string }} [opts]
 */
export function listRecipes(opts = {}) {
	const params = new URLSearchParams();
	if (opts.category) params.set('category', opts.category);
	if (opts.tag) params.set('tag', opts.tag);
	const qs = params.toString();
	return get(`/recipes${qs ? `?${qs}` : ''}`);
}

/** @param {string} q */
export function searchRecipes(q) {
	return get(`/search?q=${encodeURIComponent(q)}`);
}

/** @param {string} id */
export function getRecipe(id) {
	return get(`/recipes/${encodeURIComponent(id)}`);
}

/**
 * @param {string} markdown
 * @param {{ category?: string, source?: string }} [opts]
 */
export function createRecipe(markdown, opts = {}) {
	const body = { markdown };
	if (opts.category) body.category = opts.category;
	if (opts.source) body.source = opts.source;
	return send('POST', '/recipes', body);
}

/**
 * Import a recipe from a URL (§3.D.2). Returns an unsaved draft `{ markdown }`
 * for the editor; throws with the server's message on failure.
 * @param {string} url
 * @returns {Promise<{ markdown: string }>}
 */
export function importWebsite(url) {
	return send('POST', '/import/website', { url });
}

/**
 * What smart import can offer (§3.D.3) — gate UI on this.
 * @returns {Promise<{ llm_extraction: boolean }>}
 */
export function importCapabilities() {
	return get('/import/capabilities');
}

/**
 * Import a recipe from a photo (§3.D.3). Multipart upload; returns an unsaved
 * draft `{ markdown }` for the editor. Throws with the server's message.
 * @param {File} file
 * @returns {Promise<{ markdown: string }>}
 */
export async function importPhoto(file) {
	const body = new FormData();
	body.append('file', file);
	// No content-type header — the browser sets the multipart boundary itself.
	const res = await fetch('/api/import/photo', { method: 'POST', body });
	if (!res.ok) {
		let detail = `${res.status} ${res.statusText}`;
		try {
			const data = await res.json();
			if (data?.detail) detail = data.detail;
		} catch {
			/* non-JSON error body */
		}
		throw new Error(detail);
	}
	return res.json();
}

/**
 * @param {string} id
 * @param {string} markdown
 */
export function updateRecipe(id, markdown) {
	return send('PUT', `/recipes/${encodeURIComponent(id)}`, { markdown });
}

/** @param {string} id */
export function deleteRecipe(id) {
	return send('DELETE', `/recipes/${encodeURIComponent(id)}`);
}
