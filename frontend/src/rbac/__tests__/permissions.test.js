// can() against the whole Screen Authorization matrix (24 rows x 5 roles x 6 actions).
// The expected table is copied from the team's specification in its original notation, so it is an
// independent oracle for permissions.js. Cells changed by the team decision of 2026-11-17 (rows without
// a screen in the role's flow removed; #8 gains E for Developer) are marked `// decided`; rows #4, #14,
// #15 and #16 were removed from the web for every role and are listed in REMOVED.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ACTIONS, allowedActions, can, canAccess, PERMISSIONS, SCREEN_KEYS } from '../permissions.js';
import { ROLE_ORDER } from '../roles.js';

//    row, key,                       typical     Developer  Staff      Manager    Tech Lead  Administrator
const SPEC = [
  [1, 'authentication', 'R', '✓', '✓', '✓', '✓', '✓'],
  [2, 'profile', 'R-U', '✓', '✓', '✓', '✓', '✓'],
  [3, 'notifications', 'R', 'R', '-', '-', '-', '-'],
  [5, 'githubConnection', 'C-R-D', 'C-R-D', '-', '-', '-', '-'],
  [6, 'repositories', 'C-R-U-D', 'C-R-U-D', '-', '-', '-', 'C-R-U-D'],
  [7, 'pullRequests', 'R', 'R', '-', '-', 'R', '-'], // decided
  [8, 'documentation', 'C-R-U-E', 'C-R-U-E', 'R-U', '-', 'R', '-'], // decided
  [9, 'workflowSubmission', 'C-R', 'C-R', '-', '-', 'R', '-'], // decided
  [10, 'staffReview', 'C-R-U-A', 'R', 'C-R-U-A', 'R', 'R', '-'],
  [11, 'managerApproval', 'R-U-A', '-', '-', 'R-U-A', 'R', '-'], // decided
  [12, 'approvalPolicies', 'C-R-U', '-', '-', 'C-R-U', '-', '-'],
  [13, 'approvalAudit', 'R', '-', 'R', 'R', 'R', 'R'],
  [17, 'driftPolicies', 'C-R-U', '-', '-', '-', 'C-R-U', '-'],
  [18, 'versionHistory', 'R', 'R', 'R', '-', 'R', '-'], // decided
  [19, 'documentRollback', 'U', 'U', '-', 'U', 'U', '-'],
  [20, 'knowledgeBase', 'R', 'R', '-', '-', 'R', '-'],
  [21, 'collections', 'C-R-U-D', 'R', '-', '-', 'C-R-U-D', '-'],
  [22, 'templates', 'C-R-U-D', 'R', 'R', '-', 'C-R-U-D', '-'],
  [23, 'healthReports', 'R-E', '-', '-', '-', 'R-E', '-'],
  [24, 'userManagement', 'C-R-U-D', '-', '-', '-', '-', 'C-R-U-D'],
  [25, 'workspaceAdministration', 'C-R-U-D', '-', '-', '-', '-', 'C-R-U-D'],
  [26, 'systemConfiguration', 'C-R-U', '-', '-', '-', '-', 'C-R-U'],
  [27, 'monitoring', 'R', '-', '-', '-', '-', 'R'],
  [28, 'notificationPolicies', 'C-R-U', '-', '-', '-', '-', 'C-R-U'],
];

function parse(cell, typical) {
  if (cell === '-') return [];
  return (cell === '✓' ? typical : cell).split('-');
}

const REMOVED = ['dashboard', 'autoUpdateSettings', 'autoUpdateReview', 'driftAlerts'];

test('the matrix has the specified rows in order, keeping their original numbers', () => {
  assert.equal(SCREEN_KEYS.length, 24);
  assert.deepEqual(SCREEN_KEYS, SPEC.map(([, key]) => key));
  SPEC.forEach(([row, key]) => assert.equal(PERMISSIONS[key].row, row));
});

test('rows #4, #14, #15 and #16 are not available to any role', () => {
  for (const key of REMOVED) {
    assert.equal(PERMISSIONS[key], undefined);
    for (const role of ROLE_ORDER) assert.equal(canAccess(role, key), false, `${role} ${key}`);
  }
});

for (const [row, key, typical, ...cells] of SPEC) {
  test(`can() matches row #${row} ${key} for every role and action`, () => {
    ROLE_ORDER.forEach((role, index) => {
      const expected = parse(cells[index], typical);
      for (const action of ACTIONS) {
        assert.equal(can(role, key, action), expected.includes(action), `${role} ${key} ${action}`);
      }
      assert.equal(canAccess(role, key), expected.length > 0, `${role} access ${key}`);
    });
  });
}

test('every granted action is one of the row typical actions', () => {
  for (const key of SCREEN_KEYS) {
    for (const role of ROLE_ORDER) {
      for (const action of allowedActions(role, key)) {
        assert.ok(PERMISSIONS[key].typicalActions.includes(action), `${role} ${key} ${action}`);
      }
    }
  }
});

test('unknown roles, screens and actions are denied; legacy ADMIN is Administrator', () => {
  assert.equal(can(null, 'profile', 'R'), false);
  assert.equal(can('', 'profile', 'R'), false);
  assert.equal(can('GUEST', 'profile', 'R'), false);
  assert.equal(can('DEVELOPER', 'unknownScreen', 'R'), false);
  assert.equal(can('DEVELOPER', 'profile', 'X'), false);
  assert.equal(can('developer', 'githubConnection', 'C'), true);
  assert.equal(can('ADMIN', 'userManagement', 'D'), true);
  assert.equal(can('ADMIN', 'githubConnection', 'R'), false);
});
