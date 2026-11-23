// TODO: thay bằng screen flow chính thức của nhóm
// PROVISIONAL flow for Technical Lead. The team has not provided this flow yet, so it is built only
// from the matrix rows where Technical Lead has a permission, grouped into modules. The oversight screens
// are read only (the matrix gives this role R on them); Drift Policies & Thresholds is the one place it edits.
import { implemented, module, profileSettings } from './nodes.js';

export default Object.freeze({
  role: 'TECHNICAL_LEAD',
  provisional: true,
  landing: '/knowledge/search',
  modules: Object.freeze([
    module('account', 'Account Management', [
      profileSettings(),
    ]),
    module('code-documentation', 'Code & Documentation', [
      implemented('pr-commit-data', 'Pull Requests & Commits', '/code/activity', 'pullRequests', 'OversightRepositories'), // #7
      implemented('documentation-overview', 'Documentation', '/code/documentation', 'documentation', 'OversightDocumentation'), // #8
      implemented('workflow-status', 'Workflow Status', '/code/workflow-status', 'workflowSubmission', 'WorkflowOversight'), // #9
    ]),
    module('review-approval', 'Review & Approval', [
      implemented('staff-review-overview', 'Staff Review', '/oversight/staff-review', 'staffReview', 'WorkflowOversight'), // #10
      implemented('manager-approval-overview', 'Manager Approval', '/oversight/manager-approval', 'managerApproval', 'WorkflowOversight'), // #11
      implemented('approval-audit', 'Approval Audit Trail & History', '/oversight/audit', 'approvalAudit', 'ApprovalAudit'), // #13
    ]),
    module('drift', 'Drift', [
      implemented('drift-policies', 'Drift Policies & Thresholds', '/drift/policies', 'driftPolicies', 'OversightRepositories'), // #17
    ]),
    module('versions', 'Versions', [
      implemented('version-history', 'Version History & Comparison', '/versions/history', 'versionHistory', 'VersionExplorer'), // #18
      implemented('document-rollback', 'Document Rollback', '/versions/rollback', 'documentRollback', 'VersionExplorer'), // #19
    ]),
    module('knowledge', 'Knowledge Base', [
      implemented('documentation-collections', 'Documentation Collections', '/knowledge/collections', 'collections', 'DocumentationCollections'),
      implemented('knowledge-search', 'Knowledge Search', '/knowledge/search', 'knowledgeBase', 'DocumentationSearch'), // #20
      implemented('templates', 'Documentation Templates', '/knowledge/templates', 'templates', 'TemplateLibrary'), // #22
    ]),
    module('reports', 'Reports', [
      implemented('health-reports', 'Health Metrics, Dependency Graph & Reports', '/reports/health', 'healthReports', 'HealthReports'), // #23
    ]),
  ]),
});
