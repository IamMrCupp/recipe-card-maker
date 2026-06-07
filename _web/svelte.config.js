import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	compilerOptions: {
		// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
	},
	kit: {
		// SPA: a single fallback page boots client-side routing; data comes from the
		// FastAPI JSON API at /api. FastAPI serves this build dir in production
		// (see _app/main.py); `make web-dev` proxies /api to the backend in dev.
		adapter: adapter({ fallback: 'index.html', strict: false })
	}
};

export default config;
