// node --test worker/test
import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../src/index.js';

const calls = [];
let reply = () => new Response('{"bustime-response":{"prd":[]}}', { status: 200 });
globalThis.fetch = async (url) => { calls.push(String(url)); return reply(String(url)); };
const env = { ACT_TOKEN: 'SECRET123' };
const get = (path, e = env) => worker.fetch(new Request('https://w.example' + path), e, { waitUntil() {} });

test('health says whether a key is set', async () => {
  const r = await (await get('/health')).json();
  assert.equal(r.ok, true); assert.equal(r.key, true);
  assert.equal((await (await get('/health', {})).json()).key, false);
});

test('forwards allowed parameters, adds the key, adds CORS', async () => {
  calls.length = 0;
  const r = await get('/act/prediction?stpid=55998,55722&rt=J,FS,G&top=20&tmres=m&token=EVIL&evil=1');
  assert.equal(r.status, 200);
  assert.equal(r.headers.get('access-control-allow-origin'), '*');
  const u = new URL(calls[0]);
  assert.equal(u.origin + u.pathname, 'https://api.actransit.org/transit/actrealtime/prediction');
  assert.equal(u.searchParams.get('token'), 'SECRET123');
  assert.equal(u.searchParams.get('stpid'), '55998,55722');
  assert.equal(u.searchParams.get('evil'), null);
  assert.deepEqual(await r.json(), { 'bustime-response': { prd: [] } });
});

test('serves repeats from its cache without calling AC Transit again', async () => {
  calls.length = 0;
  await get('/act/vehicle?rt=FS&tmres=s');
  const r = await get('/act/vehicle?rt=FS&tmres=s');
  assert.equal(calls.length, 1);
  assert.equal(r.headers.get('x-source'), 'memo');
});

test('never echoes the key, and reports a rejected key plainly', async () => {
  reply = () => new Response('{"Message":"Authorization has been denied"}', { status: 401 });
  const r = await get('/act/pattern?pid=123');
  assert.equal(r.status, 502);
  const text = await r.text();
  assert.match(text, /rejected the key/);
  assert.doesNotMatch(text, /SECRET123/);
});

test('refuses unknown endpoints, odd characters, other methods, and runs without a key', async () => {
  assert.equal((await get('/act/stops')).status, 404);
  assert.equal((await get('/etc/passwd')).status, 404);
  calls.length = 0;
  reply = () => new Response('{}', { status: 200 });
  await get('/act/pattern?rt=FS%26token%3Dx');
  assert.equal(new URL(calls[0]).searchParams.get('rt'), null);
  const post = await worker.fetch(new Request('https://w.example/act/prediction', { method: 'POST' }), env, {});
  assert.equal(post.status, 405);
  const opts = await worker.fetch(new Request('https://w.example/act/prediction', { method: 'OPTIONS' }), env, {});
  assert.equal(opts.status, 204);
  assert.equal((await get('/act/prediction?stpid=1', {})).status, 503);
});

test('upstream failures become clear 502s', async () => {
  reply = () => { throw new Error('boom'); };
  assert.equal((await get('/act/prediction?stpid=55999')).status, 502);
  reply = () => new Response('<html>oops</html>', { status: 200 });
  const r = await get('/act/prediction?stpid=55990');
  assert.equal(r.status, 502);
  assert.match(await r.text(), /other than JSON/);
});
