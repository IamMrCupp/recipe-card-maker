import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// In dev, the SvelteKit server (5173) proxies API calls to the FastAPI backend
// (8000) so there's no CORS and the frontend uses same-origin /api paths exactly
// as it will in production (where FastAPI serves the built bundle).
export default defineConfig({
	plugins: [sveltekit()],
	server: {
		proxy: {
			'/api': 'http://127.0.0.1:8000',
			'/health': 'http://127.0.0.1:8000'
		}
	}
});
