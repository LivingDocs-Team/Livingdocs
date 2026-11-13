import { useEffect, useState } from 'react';
import { githubApi } from './githubApi';

function managerError(error, action) {
  if (error?.status === 401) return 'Your session expired. Sign in again to continue.';
  if (error?.status === 403) return `You are not authorized to ${action}.`;
  if (error?.status === 404) return 'This workflow or document was not found.';
  if (error?.status === 409) return 'The workflow or document version changed. Refresh the queue and try again.';
  return error?.message || `Could not ${action}. Please try again.`;
}

function formatTimestamp(value) {
  if (!value) return 'Not provided';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function Evidence({ report }) {
  const files = Array.isArray(report?.files) ? report.files : [];
  if (!files.length) return <p className="documentation-empty">No grounding evidence was returned for this version.</p>;
  return (
    <div className="suggestion-evidence-list">
      {files.map((file) => (
        <article className="documentation-version-card" key={file.path}>
          <h5><code>{file.path}</code></h5>
          <p>Generation status: {file.status || 'Not provided'}</p>
          {(file.entities || []).map((entity) => (
            <section key={`${file.path}-${entity.kind}-${entity.name}`}>
              <strong>{entity.kind}: {entity.name}</strong>
              {(entity.evidence || []).map((item) => (
                <div className="suggestion-evidence-item" key={`${item.id}-${item.path}-${item.line_start}`}>
                  <strong>{item.id} · {item.kind}</strong>
                  <code>{item.path}{item.line_start ? `:${item.line_start}` : ''}{item.line_end ? `-${item.line_end}` : ''}</code>
                  {item.excerpt && <pre>{item.excerpt}</pre>}
                </div>
              ))}
            </section>
          ))}
          {(file.context_used || []).map((item) => (
            <div className="suggestion-evidence-item" key={`${file.path}-${item.id}-${item.path}`}>
              <strong>{item.id} · Context ({item.kind})</strong>
              <code>{item.path}{item.line_start ? `:${item.line_start}` : ''}</code>
              {item.excerpt && <pre>{item.excerpt}</pre>}
            </div>
          ))}
        </article>
      ))}
    </div>
  );
}

export default function ManagerApprovalQueue({ userId, userRole }) {
  const [isOpen, setIsOpen] = useState(false);
  const [refreshIndex, setRefreshIndex] = useState(0);
  const [queuePage, setQueuePage] = useState(0);
  const [historyPage, setHistoryPage] = useState(0);
  const [queueData, setQueueData] = useState({ content: [], page: 0, size: 20, totalElements: 0, totalPages: 0, first: true, last: true });
  const [historyData, setHistoryData] = useState({ content: [], page: 0, size: 20, totalElements: 0, totalPages: 0, first: true, last: true });
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState(null);
  const [history, setHistory] = useState([]);
  const [loadedQueueKey, setLoadedQueueKey] = useState('');
  const [loadedHistoryKey, setLoadedHistoryKey] = useState('');
  const [loadedDetailKey, setLoadedDetailKey] = useState('');
  const [queueErrorState, setQueueErrorState] = useState(null);
  const [historyListErrorState, setHistoryListErrorState] = useState(null);
  const [detailErrorState, setDetailErrorState] = useState(null);
  const [evidenceErrorState, setEvidenceErrorState] = useState(null);
  const [historyErrorState, setHistoryErrorState] = useState(null);
  const [action, setAction] = useState('');
  const [actionMessage, setActionMessage] = useState(null);
  const [lastOutcome, setLastOutcome] = useState(null);
  const [rejectComment, setRejectComment] = useState('');
  const [rollbackVersion, setRollbackVersion] = useState('');
  const [rollbackReason, setRollbackReason] = useState('');

  const queue = queueData.content;
  const managerHistory = historyData.content.filter((item) => ['APPROVED', 'REJECTED'].includes(item.status));
  const approved = managerHistory.filter((item) => item.status === 'APPROVED');
  const rejected = managerHistory.filter((item) => item.status === 'REJECTED');
  const availableWorkflows = [...queue, ...managerHistory];
  const selectedWorkflowId = availableWorkflows.some((item) => String(item.id) === selectedId)
    ? selectedId : String(queue[0]?.id || managerHistory[0]?.id || '');

  const queueKey = `${userId || ''}:${userRole}:${isOpen}:${queuePage}:${refreshIndex}`;
  const historyKey = `${userId || ''}:${userRole}:${isOpen}:${historyPage}:${refreshIndex}`;
  const detailKey = `${userId || ''}:${userRole}:${isOpen}:${selectedWorkflowId}:${refreshIndex}`;
  const queueLoading = isOpen && userRole === 'MANAGER' && loadedQueueKey !== queueKey;
  const historyListLoading = isOpen && userRole === 'MANAGER' && loadedHistoryKey !== historyKey;
  const loading = queueLoading || historyListLoading;
  const detailLoading = isOpen && userRole === 'MANAGER' && Boolean(selectedWorkflowId) && loadedDetailKey !== detailKey;
  const queueError = queueErrorState?.key === queueKey ? queueErrorState.message : '';
  const historyListError = historyListErrorState?.key === historyKey ? historyListErrorState.message : '';
  const detailError = detailErrorState?.key === detailKey ? detailErrorState.message : '';
  const evidenceError = evidenceErrorState?.key === detailKey ? evidenceErrorState.message : '';
  const historyError = historyErrorState?.key === detailKey ? historyErrorState.message : '';

  useEffect(() => {
    if (!isOpen || !userId || userRole !== 'MANAGER') return undefined;
    let cancelled = false;
    githubApi(`/api/document-workflows/manager/queue?page=${queuePage}&size=20`, { userId })
      .then((result) => {
        if (cancelled) return;
        if (!Array.isArray(result?.content)) throw new Error('The Manager queue response did not include a workflow list.');
        const data = {
          content: result.content,
          page: Number.isInteger(result.page) ? result.page : queuePage,
          size: Number.isInteger(result.size) ? result.size : 20,
          totalElements: Number.isInteger(result.totalElements) ? result.totalElements : result.content.length,
          totalPages: Number.isInteger(result.totalPages) ? result.totalPages : 0,
          first: typeof result.first === 'boolean' ? result.first : queuePage === 0,
          last: typeof result.last === 'boolean' ? result.last : true,
        };
        if (data.totalPages > 0 && queuePage >= data.totalPages) {
          setQueuePage(data.totalPages - 1);
          return;
        }
        if (data.totalPages === 0 && queuePage > 0) {
          setQueuePage(0);
          return;
        }
        setQueueData(data);
        setQueueErrorState(null);
      })
      .catch((error) => {
        if (!cancelled) setQueueErrorState({ key: queueKey, message: managerError(error, 'view the Manager approval queue') });
      })
      .finally(() => { if (!cancelled) setLoadedQueueKey(queueKey); });
    return () => { cancelled = true; };
  }, [isOpen, userId, userRole, queuePage, refreshIndex, queueKey]);

  useEffect(() => {
    if (!isOpen || !userId || userRole !== 'MANAGER') return undefined;
    let cancelled = false;
    githubApi(`/api/document-workflows/history-accessible?page=${historyPage}&size=20`, { userId })
      .then((result) => {
        if (cancelled) return;
        if (!Array.isArray(result?.content)) throw new Error('The Manager history response did not include a workflow list.');
        const data = {
          content: result.content,
          page: Number.isInteger(result.page) ? result.page : historyPage,
          size: Number.isInteger(result.size) ? result.size : 20,
          totalElements: Number.isInteger(result.totalElements) ? result.totalElements : result.content.length,
          totalPages: Number.isInteger(result.totalPages) ? result.totalPages : 0,
          first: typeof result.first === 'boolean' ? result.first : historyPage === 0,
          last: typeof result.last === 'boolean' ? result.last : true,
        };
        if (data.totalPages > 0 && historyPage >= data.totalPages) {
          setHistoryPage(data.totalPages - 1);
          return;
        }
        if (data.totalPages === 0 && historyPage > 0) {
          setHistoryPage(0);
          return;
        }
        setHistoryData(data);
        setHistoryListErrorState(null);
      })
      .catch((error) => {
        if (!cancelled) setHistoryListErrorState({ key: historyKey, message: managerError(error, 'view Manager decision history') });
      })
      .finally(() => { if (!cancelled) setLoadedHistoryKey(historyKey); });
    return () => { cancelled = true; };
  }, [isOpen, userId, userRole, historyPage, refreshIndex, historyKey]);

  useEffect(() => {
    if (!isOpen || !userId || userRole !== 'MANAGER' || !selectedWorkflowId) return undefined;
    let cancelled = false;
    const base = `/api/document-workflows/${encodeURIComponent(selectedWorkflowId)}`;
    Promise.allSettled([
      githubApi(base, { userId }),
      githubApi(`${base}/document`, { userId }),
      githubApi(`${base}/evidence`, { userId }),
      githubApi(`${base}/history`, { userId }),
    ]).then(([workflowResult, documentResult, evidenceResult, historyResult]) => {
      if (cancelled) return;
      if (workflowResult.status === 'rejected') {
        setDetailErrorState({ key: detailKey, message: managerError(workflowResult.reason, 'view this workflow') });
        setDetail(null);
        setHistory([]);
        return;
      }
      setDetail({
        workflow: workflowResult.value,
        document: documentResult.status === 'fulfilled' ? documentResult.value : null,
        documentError: documentResult.status === 'rejected'
          ? managerError(documentResult.reason, 'view the document') : '',
        evidence: evidenceResult.status === 'fulfilled' ? evidenceResult.value : null,
      });
      if (evidenceResult.status === 'rejected') {
        setEvidenceErrorState({ key: detailKey, message: managerError(evidenceResult.reason, 'view document evidence') });
      }
      if (historyResult.status === 'fulfilled' && Array.isArray(historyResult.value)) {
        setHistory(historyResult.value);
      } else {
        setHistory([]);
        setHistoryErrorState({ key: detailKey, message: historyResult.status === 'rejected'
          ? managerError(historyResult.reason, 'view approval history')
          : 'The approval history response was invalid.' });
      }
    }).finally(() => { if (!cancelled) setLoadedDetailKey(detailKey); });
    return () => { cancelled = true; };
  }, [isOpen, userId, userRole, selectedWorkflowId, refreshIndex, detailKey]);

  if (!userId || userRole !== 'MANAGER') return null;

  const visibleDetail = detail?.workflow && String(detail.workflow.id) === selectedWorkflowId ? detail : null;
  const workflow = visibleDetail?.workflow;
  const canDecide = workflow?.status === 'PENDING_MANAGER_APPROVAL'
    && workflow.staffReviewResult === 'PASSED';
  const canRollback = workflow?.status === 'APPROVED';
  const repository = visibleDetail?.evidence?.source_snapshot?.repository_full_name
    || 'Not included in workflow/evidence response';

  async function submitDecision(decision, comment) {
    if (!workflow || action) return;
    setAction(decision);
    setActionMessage(null);
    try {
      const response = await githubApi(`/api/document-workflows/${encodeURIComponent(workflow.id)}/${decision === 'APPROVED' ? 'approve' : 'reject'}`, {
        method: 'POST', userId, ...(decision === 'REJECTED' ? { body: { comment: comment.trim() } } : {}),
      });
      const expected = decision;
      if (String(response?.id) !== String(workflow.id) || response?.managerDecision !== expected
        || response?.status !== (decision === 'APPROVED' ? 'APPROVED' : 'REJECTED')) {
        throw new Error('The Backend did not confirm the expected Manager decision. Refresh to verify the workflow.');
      }
      setLastOutcome(response);
      setRejectComment('');
      setActionMessage({ type: 'success', text: `Backend confirmed ${decision}.` });
      try {
        const events = await githubApi(`/api/document-workflows/${encodeURIComponent(workflow.id)}/history`, { userId });
        setHistory(Array.isArray(events) ? events : []);
      } catch (error) {
        setHistoryErrorState({ key: detailKey, message: managerError(error, 'refresh approval history') });
      }
      setRefreshIndex((value) => value + 1);
    } catch (error) {
      setActionMessage({ type: 'error', text: managerError(error, `submit ${decision.toLowerCase()} decision`) });
    } finally {
      setAction('');
    }
  }

  async function submitRollback(event) {
    event.preventDefault();
    if (!workflow || !canRollback || action) return;
    const version = Number(rollbackVersion);
    if (!Number.isInteger(version) || version < 1 || version === workflow.submittedDocumentVersion) {
      setActionMessage({ type: 'error', text: 'Choose a positive source version different from the currently approved version.' });
      return;
    }
    if (!rollbackReason.trim()) {
      setActionMessage({ type: 'error', text: 'A rollback reason is required.' });
      return;
    }
    if (!window.confirm(`Request rollback to document version ${version}? The Backend will return it to Staff review.`)) return;
    setAction('ROLLBACK');
    setActionMessage(null);
    try {
      const response = await githubApi(`/api/document-workflows/${encodeURIComponent(workflow.id)}/rollback`, {
        method: 'POST', userId, body: { sourceVersion: version, reason: rollbackReason.trim() },
      });
      if (String(response?.id) !== String(workflow.id) || response?.status !== 'PENDING_STAFF_REVIEW'
        || response?.submittedDocumentVersion == null) {
        throw new Error('The Backend did not confirm the rollback workflow transition. Refresh and verify the document.');
      }
      setLastOutcome(response);
      setRollbackVersion('');
      setRollbackReason('');
      setActionMessage({ type: 'success', text: 'Backend confirmed rollback and returned the document to Staff review.' });
      try {
        const events = await githubApi(`/api/document-workflows/${encodeURIComponent(workflow.id)}/history`, { userId });
        setHistory(Array.isArray(events) ? events : []);
      } catch (error) {
        setHistoryErrorState({ key: detailKey, message: managerError(error, 'refresh approval history') });
      }
      setRefreshIndex((value) => value + 1);
    } catch (error) {
      setActionMessage({ type: 'error', text: managerError(error, 'request rollback') });
    } finally {
      setAction('');
    }
  }

  return (
    <section className="documentation-panel manager-approval" aria-labelledby="manager-approval-heading">
      <div className="staff-review-heading">
        <div>
          <h3 id="manager-approval-heading">Manager Approval</h3>
          <p className="documentation-hint">Decisions and document access are enforced by the Backend.</p>
        </div>
        {isOpen ? (
          <div className="documentation-actions">
            <button type="button" className="documentation-secondary-button" onClick={() => setRefreshIndex((value) => value + 1)} disabled={loading}>
              {loading ? 'Refreshing...' : 'Refresh approval queue'}
            </button>
            <button type="button" className="documentation-secondary-button" onClick={() => setIsOpen(false)}>Hide approvals</button>
          </div>
        ) : (
          <button type="button" className="documentation-primary-button" onClick={() => setIsOpen(true)}>Open Manager Approval</button>
        )}
      </div>

      {lastOutcome && (
        <section className="staff-review-outcome" aria-label="Last Manager workflow result">
          <h4>Last workflow result</h4>
          <p><strong>Document:</strong> {lastOutcome.documentTitle || 'Untitled document'}</p>
          <p><strong>Manager decision:</strong> {lastOutcome.managerDecision || 'Rollback requested'}</p>
          <p><strong>Workflow status:</strong> {lastOutcome.status}</p>
          {lastOutcome.managerComment && <p><strong>Manager comment:</strong> {lastOutcome.managerComment}</p>}
        </section>
      )}
      {actionMessage && <p role={actionMessage.type === 'success' ? 'status' : 'alert'}
        className={actionMessage.type === 'success' ? 'documentation-notice' : 'documentation-error'}>{actionMessage.text}</p>}
      {isOpen && (
        <>
          {loading && <p role="status" aria-live="polite">Loading Manager approval workflows...</p>}
          {queueError && <div role="alert" className="documentation-error"><p>{queueError}</p>
            <button type="button" className="documentation-secondary-button" onClick={() => setRefreshIndex((value) => value + 1)}>Retry queue</button>
          </div>}
          {historyListError && <div role="alert" className="documentation-error"><p>{historyListError}</p>
            <button type="button" className="documentation-secondary-button" onClick={() => setRefreshIndex((value) => value + 1)}>Retry decision history</button>
          </div>}
          {!loading && !queueError && !historyListError && queueData.totalElements === 0 && historyData.totalElements === 0 && (
            <p className="documentation-empty" role="status">No documents are waiting for Manager approval.</p>
          )}
          {!loading && !queueError && !historyListError && (queue.length > 0 || managerHistory.length > 0) && (
            <div className="staff-review-layout">
              <div className="staff-review-list" aria-label="Manager approval queue">
                <section aria-label="Pending Manager decisions">
                  <h4>Waiting for approval</h4>
                  {queue.length === 0 && <p className="documentation-empty" role="status">No documents are waiting for Manager approval on this page.</p>}
                  {queue.map((item) => (
                  <button type="button" key={item.id}
                    className={`suggestion-review-card ${String(item.id) === selectedWorkflowId ? 'active' : ''}`}
                    aria-pressed={String(item.id) === selectedWorkflowId}
                    onClick={() => { setActionMessage(null); setSelectedId(String(item.id)); }}>
                    <strong>{item.documentTitle || 'Untitled document'}</strong>
                    <span>Repository: Not included in workflow response</span>
                    <span>Staff: {item.reviewerUserId || 'Unavailable'}</span>
                    <span>Staff result: {item.staffReviewResult || 'Unavailable'}</span>
                    <span>Status: {item.status}</span>
                    <time dateTime={item.updatedAt || item.createdAt || undefined}>Updated: {formatTimestamp(item.updatedAt || item.createdAt)}</time>
                  </button>
                  ))}
                  {queueData.totalPages > 0 && (
                  <div className="documentation-actions manager-pagination" role="group" aria-label="Manager approval queue pagination">
                    <button type="button" className="documentation-secondary-button" disabled={queueLoading || queueData.first || queuePage <= 0}
                      onClick={() => setQueuePage((page) => Math.max(0, page - 1))}>Previous</button>
                    <span role="status">Page {queueData.page + 1} of {queueData.totalPages} · {queueData.totalElements} pending workflow(s)</span>
                    <button type="button" className="documentation-secondary-button" disabled={queueLoading || queueData.last || queuePage + 1 >= queueData.totalPages}
                      onClick={() => setQueuePage((page) => Math.min(queueData.totalPages - 1, page + 1))}>Next</button>
                  </div>
                  )}
                </section>
                <section aria-label="Manager decision history">
                {managerHistory.length === 0 && <p className="documentation-empty" role="status">No completed Manager decisions on this history page.</p>}
                {approved.length > 0 && <>
                  <h4>Previously approved</h4>
                  {approved.map((item) => (
                    <button type="button" key={`approved-${item.id}`}
                      className={`suggestion-review-card ${String(item.id) === selectedWorkflowId ? 'active' : ''}`}
                      aria-pressed={String(item.id) === selectedWorkflowId}
                      onClick={() => { setActionMessage(null); setSelectedId(String(item.id)); }}>
                      <strong>{item.documentTitle || 'Untitled document'}</strong>
                      <span>Status: {item.status}</span>
                      <span>Version: {item.submittedDocumentVersion || 'Unavailable'}</span>
                      <time dateTime={item.updatedAt || item.createdAt || undefined}>Updated: {formatTimestamp(item.updatedAt || item.createdAt)}</time>
                    </button>
                  ))}
                </>}
                {rejected.length > 0 && <>
                  <h4>Previously rejected</h4>
                  {rejected.map((item) => (
                    <button type="button" key={`rejected-${item.id}`}
                      className={`suggestion-review-card ${String(item.id) === selectedWorkflowId ? 'active' : ''}`}
                      aria-pressed={String(item.id) === selectedWorkflowId}
                      onClick={() => { setActionMessage(null); setSelectedId(String(item.id)); }}>
                      <strong>{item.documentTitle || 'Untitled document'}</strong>
                      <span>Status: {item.status}</span>
                      <span>Decision: {item.managerDecision || 'Not included in workflow response'}</span>
                      <time dateTime={item.decidedAt || undefined}>Decision time: {formatTimestamp(item.decidedAt)}</time>
                    </button>
                  ))}
                </>}
                {historyData.totalPages > 0 && (
                  <div className="documentation-actions manager-pagination" role="group" aria-label="Manager decision history pagination">
                    <button type="button" className="documentation-secondary-button" disabled={historyListLoading || historyData.first || historyPage <= 0}
                      onClick={() => setHistoryPage((page) => Math.max(0, page - 1))}>Previous</button>
                    <span role="status">Page {historyData.page + 1} of {historyData.totalPages} · {historyData.totalElements} workflow(s)</span>
                    <button type="button" className="documentation-secondary-button" disabled={historyListLoading || historyData.last || historyPage + 1 >= historyData.totalPages}
                      onClick={() => setHistoryPage((page) => Math.min(historyData.totalPages - 1, page + 1))}>Next</button>
                  </div>
                )}
                </section>
              </div>

              <div className="staff-review-detail" aria-label="Manager approval detail">
                {detailLoading && <p role="status">Loading approval details...</p>}
                {detailError && <div role="alert" className="documentation-error"><p>{detailError}</p>
                  <button type="button" className="documentation-secondary-button" onClick={() => setRefreshIndex((value) => value + 1)}>Retry details</button>
                </div>}
                {workflow && !detailLoading && (
                  <>
                    <h4>{workflow.documentTitle || 'Untitled document'}</h4>
                    <dl className="staff-review-metadata">
                      <div><dt>Status</dt><dd>{workflow.status}</dd></div>
                      <div><dt>Repository</dt><dd>{repository}</dd></div>
                      <div><dt>Staff reviewer</dt><dd>{workflow.reviewerUserId || 'Unavailable'}</dd></div>
                      <div><dt>Staff result</dt><dd>{workflow.staffReviewResult || 'Not provided'}</dd></div>
                      <div><dt>Submitted version</dt><dd>{workflow.submittedDocumentVersion || visibleDetail.document?.version || 'Not provided'}</dd></div>
                      <div><dt>Updated</dt><dd>{formatTimestamp(workflow.updatedAt)}</dd></div>
                      <div><dt>Decision time</dt><dd>{formatTimestamp(workflow.decidedAt)}</dd></div>
                    </dl>
                    {workflow.status === 'REJECTED' && (
                      <section className="staff-review-comments" aria-label="Manager rejection reason">
                        <h5>Rejection reason</h5>
                        <p>{workflow.managerComment || 'The Backend did not provide a rejection reason.'}</p>
                      </section>
                    )}
                    {visibleDetail.documentError && <p role="alert" className="documentation-error">{visibleDetail.documentError}</p>}
                    <h5>Document for decision</h5>
                    {detail.document && <pre className="staff-review-content">{visibleDetail.document.content}</pre>}
                    <p className="documentation-hint">
                      The Manager API returns the saved document and grounding evidence. It does not expose the Staff-only suggestion comparison or a workflow-linked drift report.
                    </p>
                    {workflow.staffComment && <section className="staff-review-comments">
                      <h5>Staff review comment / change request</h5><p>{workflow.staffComment}</p>
                    </section>}
                    {workflow.managerComment && <section className="staff-review-comments">
                      <h5>Manager comment</h5><p>{workflow.managerComment}</p>
                    </section>}
                    {evidenceError && <p role="alert" className="documentation-error">{evidenceError}</p>}
                    {detail.evidence && <section>
                      <h5>Document evidence</h5>
                      {visibleDetail.evidence.source_snapshot && <p className="documentation-hint">
                        Repository: {visibleDetail.evidence.source_snapshot.repository_full_name || 'Unavailable'} · branch {visibleDetail.evidence.source_snapshot.branch || 'unknown'} · commit {visibleDetail.evidence.source_snapshot.commit_sha?.slice(0, 12) || 'unknown'}
                      </p>}
                      <Evidence report={visibleDetail.evidence} />
                    </section>}
                    {historyError && <p role="alert" className="documentation-error">{historyError}</p>}
                    <section className="staff-review-history" aria-label="Approval audit history">
                      <h5>Approval history and audit</h5>
                      {history.length === 0 ? <p className="documentation-empty">No workflow audit events were returned.</p> : (
                        <ol className="documentation-approval-history">
                          {history.map((event, index) => <li key={event.id || `${event.createdAt}-${index}`}>
                            <article className="documentation-version-card">
                              <strong>{event.action || 'Action unavailable'}</strong>
                              <p>Actor: {event.actorUserId || 'Unavailable'}{event.actorRole ? ` (${event.actorRole})` : ''}</p>
                              <p>Time: {formatTimestamp(event.createdAt)}</p>
                              <p>Workflow: {event.previousStatus || '—'} → {event.newStatus || '—'}</p>
                              {event.comment && <p>Comment: {event.comment}</p>}
                            </article>
                          </li>)}
                        </ol>
                      )}
                    </section>

                    {canDecide && userRole === 'MANAGER' && <section className="manager-approval-actions">
                      <h5>Final decision</h5>
                      <p className="documentation-hint">The Backend requires a rejection reason. Approval has no request body.</p>
                      <button type="button" className="documentation-primary-button" disabled={Boolean(action)}
                        onClick={() => submitDecision('APPROVED', '')}>
                        {action === 'APPROVED' ? 'Approving...' : 'Approve document'}
                      </button>
                      <form className="staff-review-form" onSubmit={(event) => {
                        event.preventDefault();
                        if (!rejectComment.trim()) {
                          setActionMessage({ type: 'error', text: 'A rejection reason is required.' });
                          return;
                        }
                        submitDecision('REJECTED', rejectComment);
                      }}>
                        <label htmlFor="manager-rejection-comment">Rejection reason</label>
                        <textarea id="manager-rejection-comment" value={rejectComment} maxLength={2000} required
                          onChange={(event) => setRejectComment(event.target.value)} />
                        <button type="submit" className="documentation-secondary-button" disabled={Boolean(action)}>
                          {action === 'REJECTED' ? 'Rejecting...' : 'Reject document'}
                        </button>
                      </form>
                    </section>}

                    {canRollback && userRole === 'MANAGER' && <form className="staff-review-form manager-rollback" onSubmit={submitRollback}>
                      <h5>Rollback approved document</h5>
                      <p className="documentation-hint">Rollback creates a new version and returns the workflow to Staff review. The Backend validates version availability and current document state.</p>
                      <label htmlFor="rollback-source-version">Previous source version number</label>
                      <input id="rollback-source-version" type="number" min="1" max={Math.max(1, (workflow.submittedDocumentVersion || 1) - 1)}
                        value={rollbackVersion} required onChange={(event) => setRollbackVersion(event.target.value)} />
                      <label htmlFor="rollback-reason">Rollback reason</label>
                      <textarea id="rollback-reason" value={rollbackReason} maxLength={1000} required
                        onChange={(event) => setRollbackReason(event.target.value)} />
                      <button type="submit" className="documentation-secondary-button" disabled={Boolean(action)}>
                        {action === 'ROLLBACK' ? 'Requesting rollback...' : 'Request rollback'}
                      </button>
                    </form>}
                    {workflow.status === 'PENDING_MANAGER_APPROVAL' && !canDecide && <p role="alert" className="documentation-error">
                      This workflow is not eligible for a Manager decision because the Backend did not report a passed Staff review.
                    </p>}
                  </>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
