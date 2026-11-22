// Manager screen flow (team's official flow, 3 modules): approve from one queue and set policies.
// section() sub-screens are parts of the Manager Approval page and open that page.
import { implemented, module, placeholder, profileSettings, section } from './nodes.js';

export default Object.freeze({
  role: 'MANAGER',
  provisional: false,
  landing: '/approval/queue',
  modules: Object.freeze([
    module('account', 'Account Management', [
      profileSettings(),
      implemented('github-connection', 'GitHub Connection', '/github/connection', 'githubConnection', 'GitHubConnection'),
    ]),
    module('final-approval', 'Final Approval', [
      implemented('approval-queue', 'Approval Queue', '/approval/queue', 'managerApproval', 'ManagerApprovalQueue', [
        section('approval-workspace', 'Approval Workspace', '/approval/queue/workspace', 'managerApproval'),
        section('staff-comments-evidence', 'Staff Comments & Evidence', '/approval/queue/evidence', 'staffReview'),
        section('audit-trail', 'Audit Trail', '/approval/queue/audit', 'approvalAudit'),
        section('approval-decision', 'Approval Decision', '/approval/queue/decision', 'managerApproval'),
        section('version-rollback', 'Version Rollback', '/approval/queue/rollback', 'documentRollback'),
      ]),
      // Decision history list of the Manager Approval page.
      implemented('approval-history', 'Approval History', '/approval/history', 'approvalAudit', 'ManagerApprovalQueue'),
      placeholder('approval-delegation', 'Approval Delegation', '/approval/delegation', 'managerApproval'),
    ]),
    module('approval-policies', 'Approval Policies', [
      placeholder('approval-policy', 'Approval Policy', '/policies/approval', 'approvalPolicies'),
      placeholder('merge-policy', 'Merge Policy', '/policies/merge', 'approvalPolicies'),
    ]),
  ]),
});
