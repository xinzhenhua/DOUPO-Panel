/* 豆粕驾驶舱 Service Worker（v101.50）：只做一件事——接收网页推送并弹系统通知，点通知回到页面。不缓存任何资源。 */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) { d = { title: '豆粕提醒', body: e.data ? e.data.text() : '' }; }
  const title = d.title || '豆粕提醒';
  e.waitUntil(self.registration.showNotification(title, { body: d.body || '', tag: d.tag || title, renotify: true, icon: 'icon-192.png', data: { url: d.url || './' } }));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || './';
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(cs => { for (const c of cs) { if ('focus' in c) return c.focus(); } return self.clients.openWindow(url); }));
});
