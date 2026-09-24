// McGee Morning Board live-data Worker.
// Forwards a few read-only AC Transit real-time requests with the owner's key attached, so the key never
// reaches the browser and the page gets CORS headers. Only these endpoints and parameters pass through.

const UPSTREAM = 'https://api.actransit.org/transit/actrealtime/';
const ENDPOINTS = {
  prediction: { params: ['stpid', 'rt', 'vid', 'top', 'tmres'], ttl: 15 },
  vehicle: { params: ['vid', 'rt', 'tmres'], ttl: 15 },
  pattern: { params: ['pid', 'rt'], ttl: 6 * 3600 },
  servicebulletin: { params: ['rt', 'rtdir', 'stpid'], ttl: 300 },
};
const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Max-Age': '86400',
};
const memo = new Map();                               // per-isolate cache: url -> { at, body }

function json(obj, status = 200, extra = {}) {
  return new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json; charset=utf-8', ...CORS, ...extra } });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
    if (request.method !== 'GET') return json({ error: 'GET only' }, 405);
    if (url.pathname === '/' || url.pathname === '/health') {
      return json({ ok: true, key: !!env.ACT_TOKEN, endpoints: Object.keys(ENDPOINTS) }, 200, { 'Cache-Control': 'no-store' });
    }
    const m = /^\/act\/([a-z]+)$/.exec(url.pathname);
    const spec = m && ENDPOINTS[m[1]];
    if (!spec) return json({ error: 'not found' }, 404);
    if (!env.ACT_TOKEN) return json({ error: 'no AC Transit key on the server yet' }, 503);

    const up = new URL(UPSTREAM + m[1]);
    for (const p of spec.params) {
      const v = url.searchParams.get(p);
      if (v != null && v !== '' && v.length <= 120 && /^[\w,.:-]+$/.test(v)) up.searchParams.set(p, v);
    }
    const cacheId = up.toString();                    // without the key
    const hit = memo.get(cacheId);
    if (hit && Date.now() - hit.at < spec.ttl * 1000) return json0(hit.body, spec.ttl, 'memo');

    let cache = null, cacheReq = null;
    try { cache = caches.default; cacheReq = new Request('https://cache.mcgee-board.invalid/?u=' + encodeURIComponent(cacheId)); } catch (e) { cache = null; }
    if (cache) {
      const c = await cache.match(cacheReq).catch(() => null);
      if (c) { const body = await c.text(); memo.set(cacheId, { at: Date.now(), body }); return json0(body, spec.ttl, 'edge'); }
    }

    up.searchParams.set('token', env.ACT_TOKEN);
    let res;
    try {
      res = await fetch(up.toString(), { headers: { Accept: 'application/json' } });
    } catch (e) {
      return json({ error: 'AC Transit unreachable' }, 502);
    }
    if (res.status === 401) return json({ error: 'AC Transit rejected the key' }, 502);
    if (res.status === 403) return json({ error: 'AC Transit refused the request (HTTP 403); check the key' }, 502);
    if (!res.ok) return json({ error: 'AC Transit HTTP ' + res.status }, 502);
    const body = await res.text();
    if (!/^\s*[{[]/.test(body)) return json({ error: 'AC Transit sent something other than JSON' }, 502);
    memo.set(cacheId, { at: Date.now(), body });
    if (memo.size > 200) memo.delete(memo.keys().next().value);
    if (cache && ctx && ctx.waitUntil) {
      ctx.waitUntil(cache.put(cacheReq, new Response(body, { headers: { 'Cache-Control': 'public, max-age=' + spec.ttl } })).catch(() => {}));
    }
    return json0(body, spec.ttl, 'origin');
  },
};

function json0(body, ttl, source) {
  return new Response(body, { status: 200, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'public, max-age=' + ttl, 'X-Source': source, ...CORS } });
}
