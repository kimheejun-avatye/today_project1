import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
const dir = mkdtempSync(join(tmpdir(), 'haru-client-'));
execFileSync(process.execPath, ['node_modules/typescript/bin/tsc', 'src/shared/api/client.ts', '--outDir', dir, '--target', 'ES2022', '--module', 'ES2022', '--lib', 'ES2022,DOM', '--skipLibCheck']);
const source = readFileSync(join(dir, 'client.js'), 'utf8');
after(() => rmSync(dir, { recursive: true, force: true }));
let index = 0;
async function setup() {
  globalThis.document = { cookie: 'csrf=initial' };
  let tail = Promise.resolve();
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { locks: {
    request(_name, fn) { const task = tail.then(fn); tail = task.catch(() => {}); return task; },
  } } });
  globalThis.BroadcastChannel = class { addEventListener() {} postMessage() {} };
  return import('data:text/javascript;base64,' + Buffer.from(source + `\n// ${index++}`).toString('base64'));
}
const reply = (status, body = {}) => new Response(JSON.stringify(body), { status });

test('concurrent 401 responses share refresh and retry each request once', async () => {
  const client = await setup();
  let refreshes = 0; const counts = {};
  globalThis.fetch = async path => {
    if (path.endsWith('/refresh')) { refreshes++; await new Promise(r => setTimeout(r, 5)); document.cookie = 'csrf=new'; return reply(200); }
    counts[path] = (counts[path] || 0) + 1;
    return reply(counts[path] === 1 ? 401 : 200);
  };
  await Promise.all([client.api('/one'), client.api('/two')]);
  assert.equal(refreshes, 1);
  assert.deepEqual(counts, { '/api/one': 2, '/api/two': 2 });
});

test('refresh network failure does not report expired login', async () => {
  const client = await setup(); let ended = 0;
  client.setUnauthorizedHandler(() => ended++);
  globalThis.fetch = async path => { if (path.endsWith('/refresh')) throw new TypeError('offline'); return reply(401); };
  await assert.rejects(client.api('/me'), /offline/);
  assert.equal(ended, 0);
});

test('revoked refresh ends login without retrying original write', async () => {
  const client = await setup(); let ended = 0; let writes = 0;
  client.setUnauthorizedHandler(() => ended++);
  globalThis.fetch = async path => { if (!path.endsWith('/refresh')) writes++; return reply(401); };
  await assert.rejects(client.api('/diaries/day', 'PUT', { content: 'draft' }));
  assert.equal(ended, 1); assert.equal(writes, 1);
});

test('logout waits for in-flight rotation and prevents original retry', async () => {
  const client = await setup();
  let ended = 0; client.setUnauthorizedHandler(() => ended++);
  let started, finish;
  const entered = new Promise(r => started = r);
  const gate = new Promise(r => finish = r);
  const order = [];
  globalThis.fetch = async path => {
    if (path.endsWith('/refresh')) { started(); await gate; order.push('rotated'); document.cookie = 'csrf=rotated'; return reply(200); }
    if (path.endsWith('/logout')) { order.push('logout'); return reply(200); }
    order.push('original'); return reply(401);
  };
  const pending = client.api('/me').catch(() => {});
  await entered;
  const logout = client.api('/auth/logout', 'POST');
  finish(); await Promise.all([pending, logout]);
  assert.deepEqual(order, ['original', 'rotated', 'logout']);
  assert.equal(ended, 0);
});

test('four-hour deadline and missing cookie prompt re-login', async () => {
  const client = await setup(); let ended = 0;
  client.setUnauthorizedHandler(() => ended++);
  const proof = exp => 'csrf=x.' + Buffer.from(JSON.stringify({ exp })).toString('base64url') + '.x';
  document.cookie = proof(Date.now() / 1000 + 10); client.checkLoginDeadline();
  assert.equal(ended, 0);
  document.cookie = proof(Date.now() / 1000 - 1); client.checkLoginDeadline();
  assert.equal(ended, 1);
  document.cookie = ''; client.checkLoginDeadline(); assert.equal(ended, 2);
});
