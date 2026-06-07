/// <reference types="@sveltejs/kit" />
// Basic offline shell: precache the built app + static files, serve them
// cache-first, and always hit the network for /api (recipe data).
import { build, files, version } from '$service-worker';

const CACHE = `recipe-box-${version}`;
const ASSETS = [...build, ...files];

self.addEventListener('install', (event) => {
	event.waitUntil(
		caches
			.open(CACHE)
			.then((cache) => cache.addAll(ASSETS))
			.then(() => self.skipWaiting())
	);
});

self.addEventListener('activate', (event) => {
	event.waitUntil(
		caches.keys().then(async (keys) => {
			for (const key of keys) {
				if (key !== CACHE) await caches.delete(key);
			}
			await self.clients.claim();
		})
	);
});

self.addEventListener('fetch', (event) => {
	const { request } = event;
	if (request.method !== 'GET') return;

	const url = new URL(request.url);
	if (url.origin !== self.location.origin) return;
	if (url.pathname.startsWith('/api')) return; // recipe data is always live

	event.respondWith(caches.match(request).then((cached) => cached || fetch(request)));
});
