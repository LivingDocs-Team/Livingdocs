// Developer screen flow.
// section() sub-screens are parts of their parent's existing page and open that page.
import { implemented, module, profileSettings, section } from './nodes.js';

export default Object.freeze({
  role: 'DEVELOPER',
  provisional: false,
  landing: '/github/connection',
  modules: Object.freeze([
    module('account', 'Account Management', [
      profileSettings(),
      implemented('notifications', 'Notifications', '/account/notifications', 'notifications', 'Notifications', [
        section('notification-details', 'Notification Details', '/account/notifications/details', 'notifications'),
      ]),
    ]),
    module('github', 'GitHub Integration', [
      implemented('github-connection', 'GitHub Connection', '/github/connection', 'githubConnection', 'GitHubConnection'),
      implemented('repository-list', 'Repository List', '/github/repositories', 'repositories', 'RepositoryManagement', [
        section('repository-selection', 'Repository Selection', '/github/repositories/selection', 'repositories'),
        section('repository-details', 'Repository Details', '/github/repositories/details', 'repositories'),
        section('repository-sync', 'Repository Synchronization', '/github/repositories/sync', 'repositories'),
      ]),
      // Pull requests and commits are shown per repository inside Repository Management (RepositoryActivity).
      implemented('pr-commit-list', 'PR & Commit List', '/github/activity', 'pullRequests', 'RepositoryManagement'),
      implemented('drift-alerts', 'Drift Alerts', '/drift/alerts', 'driftAlerts', 'DeveloperDriftAlerts'),
    ]),
    module('documentation', 'Documentation Generation', [
      implemented('coverage-gaps', 'Coverage Gaps', '/documentation/coverage-gaps', 'documentation', 'CoverageGaps'),
      implemented('generated-documents', 'Generated Documents', '/documentation/documents', 'documentation', 'DocumentationManagement', [
        section('preview-editor', 'Preview & Editor', '/documentation/documents/editor', 'documentation'),
        section('grounding-evidence', 'Grounding Evidence', '/documentation/documents/evidence', 'documentation'),
        section('submit-for-review', 'Submit for Review', '/documentation/documents/submit', 'workflowSubmission'),
        section('review-feedback', 'Review Feedback', '/documentation/documents/feedback', 'staffReview'),
      ]),
    ]),
    module('versions', 'Versions & Change Log', [
      // Version history, comparison and restore live in the Documentation Management editor.
      implemented('version-history', 'Version History', '/versions/history', 'versionHistory', 'DocumentationManagement', [
        section('version-comparison', 'Version Comparison', '/versions/history/compare', 'versionHistory'),
        section('document-rollback', 'Document Rollback', '/versions/history/rollback', 'documentRollback'),
      ]),
      implemented('change-log', 'Change Log', '/versions/change-log', 'versionHistory', 'ChangeLog'),
    ]),
    module('knowledge', 'Knowledge Base', [
      implemented('documentation-collections', 'Documentation Collections', '/knowledge/collections', 'collections', 'DocumentationCollections'),
      implemented('knowledge-search', 'Knowledge Search', '/knowledge/search', 'knowledgeBase', 'DocumentationSearch', [
        section('search-results', 'Search Results', '/knowledge/search/results', 'knowledgeBase'),
        section('doc-code-relationships', 'Doc-to-Code Relationships', '/knowledge/search/relationships', 'knowledgeBase'),
      ]),
      implemented('template-library', 'Template Library', '/knowledge/templates', 'templates', 'TemplateLibrary'),
    ]),
  ]),
});
