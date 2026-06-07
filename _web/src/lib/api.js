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
