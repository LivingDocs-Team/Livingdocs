import AuditTrail from './AuditTrail';
import { words } from './formatters';
import PageFrame from './rbac/PageFrame';
import useWorkflowList from './useWorkflowList';
import './InsightScreens.css';

/**
 * Approval Audit Trail & History (matrix row #13): the recorded events of every workflow the signed-in
 * user may read. Review History (Staff), Approval Audit Trail & History (Technical Lead, Administrator)
 * are the same page.
 */
export default function ApprovalAudit({ userId, node }) {
  const title = node?.label || 'Approval Audit Trail & History';
  const list = useWorkflowList(userId);
  const { page } = list;

  return (
    <PageFrame
      title={title}
      titleId="approval-audit-title"
      className="documentation-page insight-page"
      subtitle="Who did what on each document, in the order it happened."
    >
      {!list.ready && <p role="status">Loading documents…</p>}
      {list.ready && list.error && (
        <div role="alert" className="documentation-error">
          <p>{list.error}</p>
          <button type="button" onClick={list.retry}>Retry</button>
        </div>
      )}
      {list.ready && !list.error && list.workflows.length === 0 && (
        <div className="documentation-empty">
          <h2>No history yet</h2>
          <p>Documents you can access appear here once they have been submitted for review.</p>
        </div>
      )}

      {list.workflows.length > 0 && (
        <>
          <label htmlFor="audit-document">Document</label>
          <select id="audit-document" value={list.selectedId} onChange={(event) => list.select(event.target.value)}>
            {list.workflows.map((item) => (
              <option key={item.id} value={item.id}>
                {item.documentTitle || item.documentId || 'Untitled document'} · {words(item.status)}
              </option>
            ))}
          </select>
          {page && page.totalPages > 1 && (
            <nav className="insight-pager" aria-label="Document pages">
              <button type="button" disabled={page.first} onClick={() => list.setPageIndex((value) => value - 1)}>Previous</button>
              <span>Page {page.page + 1} of {page.totalPages}</span>
              <button type="button" disabled={page.last} onClick={() => list.setPageIndex((value) => value + 1)}>Next</button>
            </nav>
          )}
          <AuditTrail key={list.selectedId} workflowId={list.selectedId} userId={userId} />
        </>
      )}
    </PageFrame>
  );
}
