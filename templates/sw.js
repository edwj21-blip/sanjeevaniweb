/* SANJEEVANI service worker – Web Push only (no offline caching). */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));

self.addEventListener('push', event => {
  let data = { title: 'SANJEEVANI', body: '', url: '/' };
  try { data = Object.assign(data, event.data ? event.data.json() : {}); } catch (e) {}
  event.waitUntil(self.registration.showNotification(data.title, {
    body: data.body, data: { url: data.url }, tag: 'sanjeevani-reminder'
  }));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(self.clients.matchAll({ type: 'window' }).then(list => {
    for (const c of list) { if ('focus' in c) { c.navigate(url); return c.focus(); } }
    return self.clients.openWindow(url);
  }));
});
