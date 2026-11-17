// TODO: thay bằng screen flow chính thức của nhóm
// PROVISIONAL flow for Technical Lead. The team has not provided this flow yet, so it is built only
// from the matrix rows where Technical Lead has a permission, grouped into modules. A screen is wired
// to an existing component only when that component offers no action beyond the role's rights;
// every other screen is a placeholder.
import { implemented, module, placeholder, profileSettings } from './nodes.js';

export default Object.freeze({
  role: 'TECHNICAL_LEAD',
  provisional: true,
  landing: '/knowledge/search',
  modules: Object.freeze([
    module('account', 'Account Management', [
      profileSettings(),
    ]),
    module('code-documentation', 'Code & Documentation', [
      placeholder('pr-commit-data', 'Pull Requests & Commits', '/code/activity', 'pullRequests'), // #7
      placeholder('documentation-overview', 'Documentation', '/code/documentation', 'documentation'), // #8
      placeholder('workflow-status', 'Workflow Status', '/code/workflow-status', 'workflowSubmission'), // #9
    ]),
    module('review-approval', 'Review & Approval', [
      placeholder('staff-review-overview', 'Staff Review', '/oversight/staff-review', 'staffReview'), // #10
      placeholder('manager-approval-overview', 'Manager Approval', '/oversight/manager-approval', 'managerApproval'), // #11
      placeholder('approval-audit', 'Approval Audit Trail & History', '/oversight/audit', 'approvalAudit'), // #13
    ]),
    module('drift', 'Drift', [
      placeholder('drift-policies', 'Drift Policies & Thresholds', '/drift/policies', 'driftPolicies'), // #17
    ]),
    module('versions', 'Versions', [
      placeholder('version-history', 'Version History & Comparison', '/versions/history', 'versionHistory'), // #18
      placeholder('document-rollback', 'Document Rollback', '/versions/rollback', 'documentRollback'), // #19
    ]),
    module('knowledge', 'Knowledge Base', [
      implemented('knowledge-search', 'Knowledge Search', '/knowledge/search', 'knowledgeBase', 'DocumentationSearch'), // #20
      implemented('templates', 'Documentation Templates', '/knowledge/templates', 'templates', 'TemplateLibrary'), // #22
    ]),
    module('reports', 'Reports', [
      placeholder('health-reports', 'Health Metrics, Dependency Graph & Reports', '/reports/health', 'healthReports'), // #23
    ]),
  ]),
});
