/* 止观禅修引导 · Service Worker（PWA 离线缓存）
   2026-09-12 法师裁定：先本机 HTTPS(8778) 当场测，通过后再定长期托管。
   本 SW 让场景「装到 Pico 应用库后点开即用、离线可跑」。

   缓存策略（分两类，不可一刀切）：
   - 大体积不变资源（three.js / 模型 / 图标）：cache-first，命中即用，省流量省等待
   - HTML 与 manifest：network-first，有网取最新（法师改场景后立即生效），
     断网才回退缓存 —— 否则会出现"改了代码但 Pico 还是旧版"的坑

   ⚠️ 安全红线：TLS 私钥/证书（/vr_assets/tls/、*.pem）与后端动态接口
   （/api/vr/status、/ws/）一律不缓存、不预缓存，直接放行网络。 */

const CACHE = 'zhiguan-guided-v1';

/* 预缓存清单：安装时一次性拉取。模型 26MB，故首次安装需本机服务在线。 */
const PRECACHE = [
  '/vr?mode=guided',
  '/vr',
  '/manifest.webmanifest',
  '/vr_assets/three.module.js',
  '/vr_assets/jsm/loaders/GLTFLoader.js',
  '/vr_assets/jsm/utils/BufferGeometryUtils.js',
  '/vr_assets/icon-192.png',
  '/vr_assets/icon-512.png',
  '/api/vr/model?name=4.glb',      // 最小模型（26.84MB），引导版固定用它
];

/* 判断是否属于「绝不缓存」的敏感/动态请求 */
function isExcluded(url) {
  const p = url.pathname;
  return p.startsWith('/vr_assets/tls/') || p.endsWith('.pem')
      || p === '/api/vr/status' || p.startsWith('/ws');
}

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE)
      .then((c) => Promise.all(
        PRECACHE.map((u) => c.add(new Request(u, { cache: 'reload' }))
                            .catch((err) => console.warn('[SW] 预缓存失败', u, err)))
      ))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;                 // 只处理 GET
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;  // 只管同源
  if (isExcluded(url)) return;                      // 敏感/动态：不拦截，走网络

  const isNav = req.mode === 'navigate' || url.pathname === '/vr';
  if (isNav) {
    // HTML：network-first，断网回退缓存的引导版页面
    e.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
        return res;
      }).catch(() => caches.match(req).then((m) => m || caches.match('/vr?mode=guided')))
    );
    return;
  }

  // 其余静态资源：cache-first
  e.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy));
      return res;
    }))
  );
});
