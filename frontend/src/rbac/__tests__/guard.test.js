// Route guard: public pages, redirects to Login, 403 for other roles' screens, landing pages.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { allInternalPaths, flattenFlow, screenFlows } from '../flows/index.js';
import { normalizePath, postLoginPath, resolveRoute } from '../guard.js';
import { ROLE_ORDER } from '../roles.js';

const INTERNAL = [...allInternalPaths()];

test('signed out: only Home, Login and Register are reachable', () => {
  assert.deepEqual(resolveRoute({ path: '/', isAuthenticated: false }), { kind: 'public', page: 'home' });
  assert.deepEqual(resolveRoute({ path: '/login', isAuthenticated: false }), { kind: 'public', page: 'login' });
  assert.deepEqual(resolveRoute({ path: '/register', isAuthenticated: false }), { kind: 'public', page: 'register' });
  for (const path of [...INTERNAL, '/no-such-page']) {
    assert.deepEqual(resolveRoute({ path, role: 'DEVELOPER', isAuthenticated: false }), { kind: 'redirect', to: '/login' }, path);
  }
});

for (const role of ROLE_ORDER) {
  test(`${role}: own screens open, every other internal screen is 403`, () => {
    const own = new Map(flattenFlow(screenFlows[role]).map(({ node, trail }) => [node.path, { node, trail }]));
    for (const path of INTERNAL) {
      const decision = resolveRoute({ path, role, isAuthenticated: true });
      if (own.has(path)) {
        assert.equal(decision.kind, 'screen', path);
        assert.equal(decision.node, own.get(path).node);
        assert.equal(decision.trail.at(-1), decision.node);
        assert.equal(decision.trail[0].type, 'module');
      } else {
        assert.deepEqual(decision, { kind: 'forbidden' }, path);
      }
    }
  });

  test(`${role}: public pages and unknown URLs redirect to the landing page`, () => {
    const landing = screenFlows[role].landing;
    for (const path of ['/', '/login', '/register', '/no-such-page']) {
      assert.deepEqual(resolveRoute({ path, role, isAuthenticated: true }), { kind: 'redirect', to: landing }, path);
    }
    assert.equal(resolveRoute({ path: landing, role, isAuthenticated: true }).kind, 'screen');
  });
}

test('Register is Developer-only: no internal flow offers it and it is public', () => {
  for (const role of ROLE_ORDER) {
    assert.ok(!flattenFlow(screenFlows[role]).some(({ node }) => /register/i.test(node.path + node.label)), role);
  }
});

test('signed in without a known role', () => {
  assert.deepEqual(resolveRoute({ path: '/dashboard', role: '', isAuthenticated: true }), { kind: 'no-role' });
  assert.deepEqual(resolveRoute({ path: '/', role: 'GUEST', isAuthenticated: true }), { kind: 'no-role' });
  assert.equal(resolveRoute({ path: '/approval/queue', role: 'ADMIN', isAuthenticated: true }).kind, 'forbidden');
});

test('post-login target keeps an allowed requested page, otherwise uses the landing page', () => {
  assert.equal(postLoginPath('STAFF', '/review/queue/decision'), '/review/queue/decision');
  assert.equal(postLoginPath('STAFF', '/approval/queue'), '/review/queue');
  assert.equal(postLoginPath('MANAGER', null), '/approval/queue');
  assert.equal(postLoginPath('DEVELOPER', '/login'), '/github/connection');
});

test('paths are normalised', () => {
  assert.equal(normalizePath(''), '/');
  assert.equal(normalizePath('review/queue/'), '/review/queue');
  assert.equal(resolveRoute({ path: '/review/queue/', role: 'STAFF', isAuthenticated: true }).kind, 'screen');
});
