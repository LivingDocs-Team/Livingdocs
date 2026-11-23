import AuditTrail from './AuditTrail';
import { formatTime, words } from './formatters';
import PageFrame from './rbac/PageFrame';
import useWorkflowList from './useWorkflowList';
import './InsightScreens.css';

// Which workflows each oversight screen shows (keys are the screen keys of the Technical Lead flow).
const SCOPES = {
  'workflow-status': {
    title: 'Workflow Status',
    subtitle: 'Where every document is in the review and approval process.',
    statuses: null,
  },
  'staff-review-overview': {
    title: 'Staff Review',
    subtitle: 'Documents waiting for, or going through, Staff review. View only.',
    statuses: ['PENDING_STAFF_REVIEW', 'STAFF_REVIEWING', 'CHANGES_REQUESTED'],
  },
  'manager-approval-overview': {
    title: 'Manager Approval',
    subtitle: 'Documents waiting for, or decided by, a Manager. View only.',
    statuses: ['PENDING_MANAGER_APPROVAL', 'APPROVED', 'REJECTED'],
  },
};

function Detail({ workflow }) {
  const rows = [
    ['Status', words(workflow.status)],
    ['Owner', workflow.ownerUserId],
    ['Submitted version', workflow.submittedDocumentVersion],
    ['Submitted', workflow.submittedAt && formatTime(workflow.submittedAt)],
    ['Staff reviewer', workflow.reviewerUserId],
    ['Staff result', workflow.staffReviewResult && words(workflow.staffReviewResult)],
    ['Staff comment', workflow.staffComment],
    ['Manager', workflow.managerUserId],
    ['Manager decision', workflow.managerDecision && words(workflow.managerDecision)],
    ['Manager comment', workflow.managerComment],
    ['Last updated', workflow.updatedAt && formatTime(workflow.updatedAt)],
  ].filter(([, value]) => value !== null && value !== undefined && value !== '');
  return (
    <section className="notification-details" aria-label="Workflow details">
      <h2>{workflow.documentTitle || workflow.documentId || 'Untitled document'}</h2>
      <dl>
        {rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{String(value)}</dd></div>)}
      </dl>
    </section>
  );
}

/**
 * Workflow Status, Staff Review and Manager Approval for the Technical Lead (matrix rows #9, #10, #11, read only):
 * the workflows grouped by status, with the details and the audit trail of the selected one.
 */
export default function WorkflowOversight({ userId, node }) {
  const scope = SCOPES[node?.key] || SCOPES['workflow-status'];
  const list = useWorkflowList(userId, scope.statuses ? (item) => scope.statuses.includes(item.status) : null);
  const counts = list.workflows.reduce((all, item) => ({ ...all, [item.status]: (all[item.status] || 0) + 1 }), {});
  const { page } = list;

  return (
    <PageFrame title={scope.title} titleId="workflow-oversight-title" className="documentation-page insight-page"
      subtitle={scope.subtitle}>
      {!list.ready && <p role="status">Loading workflows…</p>}
      {list.ready && list.error && (
        <div role="alert" className="documentation-error">
          <p>{list.error}</p>
          <button type="button" onClick={list.retry}>Retry</button>
        </div>
      )}
      {list.ready && !list.error && list.workflows.length === 0 && (
        <div className="documentation-empty">
          <h2>Nothing here yet</h2>
          <p>No workflows match this view.</p>
        </div>
      )}

      {list.workflows.length > 0 && (
        <>
          <ul className="insight-counts" aria-label="Workflows by status">
            {Object.entries(counts).map(([status, count]) => (
              <li key={status}><strong>{count}</strong> {words(status)}</li>
            ))}
          </ul>
          <label htmlFor="oversight-workflow">Document</label>
          <select id="oversight-workflow" value={list.selectedId} onChange={(event) => list.select(event.target.value)}>
            {list.workflows.map((item) => (
              <option key={item.id} value={item.id}>
                {item.documentTitle || item.documentId || 'Untitled document'} · {words(item.status)}
              </option>
            ))}
          </select>
          {page && page.totalPages > 1 && (
            <nav className="insight-pager" aria-label="Workflow pages">
              <button type="button" disabled={page.first} onClick={() => list.setPageIndex((value) => value - 1)}>Previous</button>
              <span>Page {page.page + 1} of {page.totalPages}</span>
              <button type="button" disabled={page.last} onClick={() => list.setPageIndex((value) => value + 1)}>Next</button>
            </nav>
          )}
          {list.selected && <Detail workflow={list.selected} />}
          <h2>History</h2>
          <AuditTrail key={list.selectedId} workflowId={list.selectedId} userId={userId} />
        </>
      )}
    </PageFrame>
  );
}
