// Staff screen flow (team's official flow, 2 modules): every document is reviewed from one queue.
// section() sub-screens are parts of the Staff Review Queue page and open that page.
import { implemented, module, placeholder, profileSettings, section } from './nodes.js';

export default Object.freeze({
  role: 'STAFF',
  provisional: false,
  landing: '/review/queue',
  modules: Object.freeze([
    module('account', 'Account Management', [
      profileSettings(),
    ]),
    module('document-review', 'Document Review', [
      implemented('review-queue', 'Review Queue', '/review/queue', 'staffReview', 'StaffReviewQueue', [
        section('review-workspace', 'Review Workspace', '/review/queue/workspace', 'staffReview'),
        section('review-grounding-evidence', 'Grounding Evidence', '/review/queue/evidence', 'staffReview'),
        placeholder('review-change-log', 'Change Log', '/review/queue/change-log', 'versionHistory'),
        section('review-version-comparison', 'Version Comparison', '/review/queue/compare', 'versionHistory'),
        placeholder('template-code-check', 'Template & Code Check', '/review/queue/template-check', 'templates'),
        section('comments-change-requests', 'Comments & Change Requests', '/review/queue/comments', 'staffReview'),
        // The AI Suggestion Review editor (proposal editing) lives in the Documentation Management page.
        implemented('document-editor', 'Document Editor', '/review/queue/editor', 'documentation', 'DocumentationManagement'),
        section('review-decision', 'Review Decision', '/review/queue/decision', 'staffReview'),
      ]),
      implemented('review-history', 'Review History', '/review/history', 'approvalAudit', 'ApprovalAudit'),
    ]),
  ]),
});
