// Screen Authorization matrix: the single source of truth for what each role may do on each screen.
// Actions: C=create, R=read, U=update, D=delete (deactivate for accounts), A=approve/reject, E=export.
// A cell is a string of action letters, '✓' (every Typical Action of the row) or '' (no access).
// Column order: Developer | Staff | Manager | Technical Lead | Administrator.
// To change a permission, edit this table only; menus, route guards and <Can> read from it.
// Team decision 2026-11-17 (differs from the original specification table):
//  - rows without a screen in the role's official flow are removed: Developer #11; Staff #7, #9, #11, #15,
//    #16; Manager #7, #8, #9, #15, #16, #18.
//  - #8 gains E (Export Markdown in the document editor), for Developer only.
//  - rows #4, #14 and #15 are removed from the web; P0-06 restores #16 for Developer.
import { normalizeRole, ROLE_ORDER } from './roles.js';

export const ACTIONS = Object.freeze(['C', 'R', 'U', 'D', 'A', 'E']);

const FULL = '✓';

//   row, key,                       label,                                               typical, DEV,     STAFF,  MANAGER, TECH LEAD, ADMIN
const ROWS = [
  [1, 'authentication', 'Authentication', 'R', FULL, FULL, FULL, FULL, FULL],
  [2, 'profile', 'Own Profile & Notification Preferences', 'RU', FULL, FULL, FULL, FULL, FULL],
  [3, 'notifications', 'Notifications', 'R', 'R', '', '', '', ''],
  [5, 'githubConnection', 'GitHub Connection', 'CRD', 'CRD', '', '', '', ''],
  [6, 'repositories', 'Repository Management & Synchronization', 'CRUD', 'CRUD', '', '', '', 'CRUD'],
  [7, 'pullRequests', 'Pull Request & Commit data', 'R', 'R', '', '', 'R', ''],
  [8, 'documentation', 'Documentation Generation & Editing', 'CRUE', 'CRUE', 'RU', '', 'R', ''],
  [9, 'workflowSubmission', 'Submit for Review & Workflow Status', 'CR', 'CR', '', '', 'R', ''],
  [10, 'staffReview', 'Staff Review (queue, comments, decision)', 'CRUA', 'R', 'CRUA', 'R', 'R', ''],
  [11, 'managerApproval', 'Manager Approval (decision, delegation)', 'RUA', '', '', 'RUA', 'R', ''],
  [12, 'approvalPolicies', 'Approval & Merge Policies', 'CRU', '', '', 'CRU', '', ''],
  [13, 'approvalAudit', 'Approval Audit Trail & History', 'R', '', 'R', 'R', 'R', 'R'],
  [16, 'driftAlerts', 'Drift Alerts', 'CRU', 'CRU', '', '', '', ''],
  [17, 'driftPolicies', 'Drift Policies & Thresholds', 'CRU', '', '', '', 'CRU', ''],
  [18, 'versionHistory', 'Version History, Change Log & Comparison', 'R', 'R', 'R', '', 'R', ''],
  [19, 'documentRollback', 'Document Rollback', 'U', 'U', '', 'U', 'U', ''],
  [20, 'knowledgeBase', 'Knowledge Base (search, relationships, browse)', 'R', 'R', '', '', 'R', ''],
  [21, 'collections', 'Documentation Collections & Ownership', 'CRUD', 'R', '', '', 'CRUD', ''],
  [22, 'templates', 'Documentation Templates', 'CRUD', 'R', 'R', '', 'CRUD', ''],
  [23, 'healthReports', 'Health Metrics, Dependency Graph & Reports', 'RE', '', '', '', 'RE', ''],
  [24, 'userManagement', 'User, Role & Permission Management', 'CRUD', '', '', '', '', 'CRUD'],
  [25, 'workspaceAdministration', 'Workspace & Repository Administration', 'CRUD', '', '', '', '', 'CRUD'],
  [26, 'systemConfiguration', 'System Configuration', 'CRU', '', '', '', '', 'CRU'],
  [27, 'monitoring', 'Monitoring, Audit Logs & Analytics', 'R', '', '', '', '', 'R'],
  [28, 'notificationPolicies', 'Notification Policies', 'CRU', '', '', '', '', 'CRU'],
];

function expand(cell, typical) {
  return Object.freeze([...(cell === FULL ? typical : cell)]);
}

/** Screen key -> { row, key, label, typicalActions, roles: { ROLE: ['C', ...] } } */
export const PERMISSIONS = Object.freeze(Object.fromEntries(ROWS.map(([row, key, label, typical, ...cells]) => [
  key,
  Object.freeze({
    row,
    key,
    label,
    typicalActions: expand(typical, typical),
    roles: Object.freeze(Object.fromEntries(ROLE_ORDER.map((role, index) => [role, expand(cells[index], typical)]))),
  }),
])));

export const SCREEN_KEYS = Object.freeze(Object.keys(PERMISSIONS));

/** Actions the role may perform on the screen (empty array when it has no access). */
export function allowedActions(role, screenKey) {
  const normalized = normalizeRole(role);
  const entry = PERMISSIONS[screenKey];
  if (!normalized || !entry) return [];
  return entry.roles[normalized];
}

/** can('DEVELOPER', 'githubConnection', 'C') === true */
export function can(role, screenKey, action) {
  return allowedActions(role, screenKey).includes(action);
}

/** A role may open a screen when it has at least one action on it (e.g. Document Rollback is U only). */
export function canAccess(role, screenKey) {
  return allowedActions(role, screenKey).length > 0;
}
