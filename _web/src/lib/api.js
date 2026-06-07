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
