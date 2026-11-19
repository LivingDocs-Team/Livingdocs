// Screen flows: shape, mapping to the matrix and the menus of the team's official flows.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { flattenFlow, screenFlows } from '../flows/index.js';
import { canAccess, PERMISSIONS, SCREEN_KEYS } from '../permissions.js';
import { ROLE_ORDER } from '../roles.js';

// Module > Screen > (sub-screens), as written in the team's screen flows.
const OFFICIAL_MENUS = {
  DEVELOPER: {
    'Account Management': ['Profile & Settings', ['Profile', 'Notification Preferences'], 'Notifications', ['Notification Details']],
    'GitHub Integration': ['GitHub Connection', 'Repository List',
      ['Repository Selection', 'Repository Details', 'Repository Synchronization'], 'PR & Commit List'],
    'Documentation Generation': ['Coverage Gaps', 'Generated Documents',
      ['Preview & Editor', 'Grounding Evidence', 'Submit for Review', 'Review Feedback']],
    'Versions & Change Log': ['Version History', ['Version Comparison', 'Document Rollback'], 'Change Log'],
    'Knowledge Base': ['Documentation Collections', 'Knowledge Search', ['Search Results', 'Doc-to-Code Relationships'], 'Template Library'],
  },
  STAFF: {
    'Account Management': ['Profile & Settings', ['Profile', 'Notification Preferences']],
    'Document Review': ['Review Queue', ['Review Workspace', 'Grounding Evidence', 'Change Log', 'Version Comparison',
      'Template & Code Check', 'Comments & Change Requests', 'Document Editor', 'Review Decision'], 'Review History'],
  },
  MANAGER: {
    'Account Management': ['Profile & Settings', ['Profile', 'Notification Preferences']],
    'Final Approval': ['Approval Queue', ['Approval Workspace', 'Staff Comments & Evidence', 'Audit Trail',
      'Approval Decision', 'Version Rollback'], 'Approval History', 'Approval Delegation'],
    'Approval Policies': ['Approval Policy', 'Merge Policy'],
  },
};

function menuOf(flow) {
  const toList = (nodes) => nodes.flatMap((node) => (
    node.children.length ? [node.label, toList(node.children)] : [node.label]));
  return Object.fromEntries(flow.modules.map((moduleNode) => [moduleNode.label, toList(moduleNode.children)]));
}

test('every role has a flow and every flow names its role', () => {
  assert.deepEqual(Object.keys(screenFlows).sort(), [...ROLE_ORDER].sort());
  for (const role of ROLE_ORDER) assert.equal(screenFlows[role].role, role);
});

for (const role of Object.keys(OFFICIAL_MENUS)) {
  test(`${role} menu matches the team's official flow exactly`, () => {
    assert.deepEqual(menuOf(screenFlows[role]), OFFICIAL_MENUS[role]);
    assert.equal(screenFlows[role].provisional, false);
  });
}

for (const role of ROLE_ORDER) {
  const flow = screenFlows[role];
  const screens = flattenFlow(flow).map(({ node }) => node);

  test(`${role} flow: unique keys and paths, valid status, permission keys the role can access`, () => {
    assert.equal(new Set(screens.map((node) => node.key)).size, screens.length, 'duplicate key');
    assert.equal(new Set(screens.map((node) => node.path)).size, screens.length, 'duplicate path');
    for (const node of screens) {
      assert.ok(node.path.startsWith('/') && !['/', '/login', '/register'].includes(node.path), node.path);
      assert.ok(SCREEN_KEYS.includes(node.permissionKey), `${node.key} -> ${node.permissionKey}`);
      assert.ok(canAccess(role, node.permissionKey), `${role} cannot access ${node.key} (${node.permissionKey})`);
      assert.ok(['implemented', 'placeholder'].includes(node.status), node.key);
      assert.equal(Boolean(node.component), node.status === 'implemented', node.key);
    }
    assert.ok(screens.some((node) => node.path === flow.landing), `landing ${flow.landing} is not in the flow`);
  });
}

for (const role of ROLE_ORDER) {
  test(`${role} flow covers exactly the matrix rows the role can access`, () => {
    const flow = screenFlows[role];
    assert.equal(flow.provisional, ['TECHNICAL_LEAD', 'ADMINISTRATOR'].includes(role));
    const used = new Set(flattenFlow(flow).map(({ node }) => node.permissionKey));
    // Authentication (#1) is served by the public Login/Register pages, not by a menu item.
    const granted = SCREEN_KEYS.filter((key) => key !== 'authentication' && canAccess(role, key));
    assert.deepEqual([...used].sort(), granted.sort());
    assert.ok(PERMISSIONS.authentication.roles[role].length > 0);
  });
}
