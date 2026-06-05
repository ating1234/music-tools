const CACHE = 'music-tools-v1';
const SHELL = ['/', '/index.html', '/icon.svg', '/manifest.webmanifest'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(SHELL).catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  
  const url = new URL(e.request.url);
  if (url.pathname.startsWith('/api/')) return;

  const isHtml = url.pathname === '/' || url.pathname === '/index.html' || url.pathname.endsWith('.html');

  if (isHtml) {
    // HTML 頁面採用 Network-First 策略，確保拿到最新版，網路中斷時才使用快取備份
    e.respondWith(
      fetch(e.request).then(res => {
        if (res.ok) {
          caches.open(CACHE).then(c => c.put(e.request, res.clone())).catch(() => {});
        }
        return res;
      }).catch(() => caches.match(e.request))
    );
  } else {
    // 其他靜態資源採用 Cache-First 策略
    e.respondWith(
      caches.match(e.request).then(cached => cached || fetch(e.request).then(res => {
        if (res.ok && e.request.url.startsWith(self.location.origin)) {
          caches.open(CACHE).then(c => c.put(e.request, res.clone())).catch(() => {});
        }
        return res;
      }))
    );
  }
});
