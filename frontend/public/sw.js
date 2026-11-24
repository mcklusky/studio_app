// Minimal service worker so phones offer "Install app". It caches nothing: every request goes to the
// network as normal, so staff always see live figures and nobody gets a stale version of the app.
self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()))
self.addEventListener('fetch', () => {})
