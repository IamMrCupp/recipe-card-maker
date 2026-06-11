// Thin client for the FastAPI JSON API (served same-origin under /api).

/** @param {string} path */
async function get(path) {
	const res = await fetch(`/api${path}`);
	if (!res.ok) {
		if (redirectOn401(res)) return new Promise(() => {}); // navigation takes over
		throw new Error(`${res.status} ${res.statusText}`);
	}
	return res.json();
}

/**
 * A 401 means the session is missing/expired (hosted mode) — bounce to the
 * login page instead of surfacing a raw error. No-op when already there.
 * @param {Response} res
 */
function redirectOn401(res) {
	if (res.status === 401 && !window.location.pathname.startsWith('/login')) {
		window.location.href = '/login';
		return true;
	}
	return false;
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
		if (redirectOn401(res)) return new Promise(() => {}); // navigation takes over
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
 * POST a single file as multipart/form-data. No content-type header — the
 * browser sets the multipart boundary itself. Unwraps the server's error detail.
 * @param {string} path
 * @param {File} file
 */
async function postFile(path, file) {
	const body = new FormData();
	body.append('file', file);
	const res = await fetch(`/api${path}`, { method: 'POST', body });
	if (!res.ok) {
		if (redirectOn401(res)) return new Promise(() => {}); // navigation takes over
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
 * Import a recipe from pasted text (§3.D.4). Returns an unsaved draft `{ markdown }`
 * for the editor; throws with the server's message on failure.
 * @param {string} text
 * @returns {Promise<{ markdown: string }>}
 */
export function importSocial(text) {
	return send('POST', '/import/social', { text });
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
export function importPhoto(file) {
	return postFile('/import/photo', file);
}

/**
 * Attach an image to a recipe (§3.E.1). Returns the updated recipe detail.
 * @param {string} id
 * @param {File} file
 * @returns {Promise<{ images: string[] }>}
 */
export function attachImage(id, file) {
	return postFile(`/recipes/${encodeURIComponent(id)}/images`, file);
}

/**
 * Detach an image from a recipe by its ref (the trailing segment of its URL).
 * @param {string} id
 * @param {string} ref
 */
export function deleteImage(id, ref) {
	return send('DELETE', `/recipes/${encodeURIComponent(id)}/images/${encodeURIComponent(ref)}`);
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

/**
 * Session probe (Phase 4α). `auth_enabled: false` means local/dev mode.
 * @returns {Promise<{ auth_enabled: boolean, authenticated: boolean }>}
 */
export function authStatus() {
	return get('/auth/me');
}

/** @param {string} password */
export function login(password) {
	return send('POST', '/auth/login', { password });
}

export function logout() {
	return send('POST', '/auth/logout');
}
