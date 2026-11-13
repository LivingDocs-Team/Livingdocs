import { useCallback, useEffect, useState } from 'react';
import { githubApi } from './githubApi';

function errorMessage(error, action) {
  if (error?.status === 401) return 'Your session expired. Sign in again to continue.';
  if (error?.status === 403) return `You are not authorized to ${action}.`;
  if (error?.status === 404) return 'This workflow is no longer available.';
  if (error?.status === 409) return 'This workflow changed or was claimed by another Staff member. Refresh the queue.';
  return error?.message || `Could not ${action}. Please try again.`;
}

function formatTimestamp(value) {
  if (!value) return 'Not provided';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function DiffView({ diff }) {
  if (!diff) return <p className="documentation-empty">No comparison diff was returned.</p>;
  return (
    <pre className="suggestion-diff" aria-label="Backend unified content diff">
      {diff.split(/\r?\n/).map((line, index) => {
        const kind = line.startsWith('+++') || line.startsWith('---') || line.startsWith('@@')
          ? 'meta' : line.startsWith('+') ? 'added' : line.startsWith('-') ? 'removed' : 'context';
        return <span className={`suggestion-diff-line suggestion-diff-${kind}`} key={`${index}-${line}`}>{line || ' '}{'\n'}</span>;
      })}
    </pre>
  );
}

function Evidence({ report }) {
  const files = Array.isArray(report?.files) ? report.files : [];
  if (!files.length) return <p className="documentation-empty">No source evidence is available.</p>;
  return (
    <div className="suggestion-evidence-list">
      {files.map((file) => (
        <article className="documentation-version-card" key={file.path}>
          <h5><code>{file.path}</code></h5>
          <p>Status: {file.status || 'Not provided'}</p>
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

export default function StaffReviewQueue({ userId }) {
  const [queueOpen, setQueueOpen] = useState(false);
  const [queue, setQueue] = useState({ content: [], page: 0, size: 20, totalElements: 0, totalPages: 0, first: true, last: true });
  const [pageIndex, setPageIndex] = useState(0);
  const [loadedQueueKey, setLoadedQueueKey] = useState('');
  const [queueErrorState, setQueueErrorState] = useState(null);
  const [refreshIndex, setRefreshIndex] = useState(0);
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState(null);
  const [loadedDetailKey, setLoadedDetailKey] = useState('');
  const [detailErrorState, setDetailErrorState] = useState(null);
  const [action, setAction] = useState('');
  const [actionMessage, setActionMessage] = useState(null);
  const [reviewOutcome, setReviewOutcome] = useState(null);
  const [reviewResult, setReviewResult] = useState('');
  const [reviewComment, setReviewComment] = useState('');

  const queueKey = `${userId || ''}:${queueOpen}:${pageIndex}:${refreshIndex}`;
  const detailKey = `${userId || ''}:${queueOpen}:${selectedId}:${refreshIndex}`;
  const isLoadingQueue = Boolean(userId && queueOpen) && loadedQueueKey !== queueKey;
  const queueError = queueErrorState?.key === queueKey ? queueErrorState.message : '';
  const detailLoading = Boolean(userId && queueOpen && selectedId) && loadedDetailKey !== detailKey;
  const detailError = detailErrorState?.key === detailKey ? detailErrorState.message : '';

  const refreshQueue = useCallback(() => setRefreshIndex((value) => value + 1), []);

  useEffect(() => {
    if (!userId || !queueOpen) return undefined;
    let cancelled = false;
    githubApi(`/api/document-workflows/staff/queue?page=${pageIndex}&size=20`, { userId })
      .then((result) => {
        if (cancelled) return;
        if (!Array.isArray(result?.content)) throw new Error('The Staff queue response did not include a workflow list.');
        const content = result.content;
        setQueue({
          content,
          page: result?.page ?? 0,
          size: result?.size ?? 20,
          totalElements: result?.totalElements ?? content.length,
          totalPages: result?.totalPages ?? (content.length ? 1 : 0),
          first: result?.first ?? true,
          last: result?.last ?? true,
        });
        setSelectedId((current) => (content.some((item) => String(item.id) === current)
          ? current : String(content[0]?.id || '')));
      })
      .catch((error) => {
        if (cancelled) return;
        setQueue({ content: [], page: 0, size: 20, totalElements: 0, totalPages: 0, first: true, last: true });
        setSelectedId('');
        setQueueErrorState({ key: queueKey, message: errorMessage(error, 'view the Staff review queue') });
      })
      .finally(() => { if (!cancelled) setLoadedQueueKey(queueKey); });
    return () => { cancelled = true; };
  }, [userId, queueOpen, pageIndex, refreshIndex, queueKey]);

  useEffect(() => {
    if (!userId || !queueOpen || !selectedId) return undefined;
    let cancelled = false;
    const prefix = `/api/document-workflows/${encodeURIComponent(selectedId)}`;
    Promise.allSettled([
      githubApi(prefix, { userId }),
      githubApi(`${prefix}/document`, { userId }),
    ]).then(async ([workflowResult, contentResult]) => {
      if (cancelled) return;
      if (workflowResult.status === 'rejected') {
        setDetailErrorState({ key: detailKey, message: errorMessage(workflowResult.reason, 'view this workflow') });
        setDetail(null);
        return;
      }
      const workflow = workflowResult.value;
      const content = contentResult.status === 'fulfilled' ? contentResult.value : null;
      const isAssigned = workflow?.status === 'STAFF_REVIEWING' && String(workflow.reviewerUserId) === String(userId);
      let comparison = null;
      let evidence = null;
      let comparisonError = '';
      let evidenceError = '';
      if (isAssigned) {
        const [comparisonResult, evidenceResult] = await Promise.allSettled([
          githubApi(`${prefix}/review-comparison`, { userId }),
          githubApi(`${prefix}/review-evidence`, { userId }),
        ]);
        if (cancelled) return;
        comparison = comparisonResult.status === 'fulfilled' ? comparisonResult.value : null;
        evidence = evidenceResult.status === 'fulfilled' ? evidenceResult.value : null;
        comparisonError = comparisonResult.status === 'rejected'
          ? errorMessage(comparisonResult.reason, 'view the document comparison') : '';
        evidenceError = evidenceResult.status === 'rejected'
          ? errorMessage(evidenceResult.reason, 'view review evidence') : '';
      }
      setDetail({ workflow, content, contentError: contentResult.status === 'rejected'
        ? errorMessage(contentResult.reason, 'view document content') : '', comparison, evidence, comparisonError, evidenceError });
      setReviewResult('');
      setReviewComment(workflow?.staffComment || '');
      }).catch((error) => {
      if (!cancelled) setDetailErrorState({ key: detailKey, message: errorMessage(error, 'load this workflow') });
    }).finally(() => { if (!cancelled) setLoadedDetailKey(detailKey); });
    return () => { cancelled = true; };
  }, [userId, queueOpen, selectedId, refreshIndex, detailKey]);

  const selectedWorkflow = detail?.workflow;
  const assignedToMe = selectedWorkflow?.status === 'STAFF_REVIEWING'
    && String(selectedWorkflow.reviewerUserId) === String(userId);

  async function runAction(actionName, endpoint, expectedStatus, body) {
    if (!selectedId || action) return;
    setAction(actionName);
    setActionMessage(null);
    try {
      const result = await githubApi(`/api/document-workflows/${encodeURIComponent(selectedId)}/${endpoint}`, {
        method: 'POST', userId, ...(body ? { body } : {}),
      });
      if (String(result?.id) !== String(selectedId) || result?.status !== expectedStatus) {
        throw new Error('The Backend response did not confirm the expected workflow status. Refresh and verify the workflow.');
      }
      setActionMessage({ type: 'success', text: actionName === 'claim' ? 'Workflow claimed.'
        : actionName === 'release' ? 'Workflow released.' : `Review submitted: ${result.staffReviewResult}.` });
      if (actionName === 'review') {
        setReviewOutcome(result);
        setDetail((current) => current ? { ...current, workflow: result } : current);
        setReviewComment(result.staffComment || '');
        setReviewResult('');
      } else {
        setDetail((current) => current ? { ...current, workflow: result } : current);
      }
      refreshQueue();
    } catch (error) {
      setActionMessage({ type: 'error', text: errorMessage(error, `${actionName} this workflow`) });
    } finally {
      setAction('');
    }
  }

  function submitReview(event) {
    event.preventDefault();
    if (!['PASSED', 'CHANGES_REQUESTED'].includes(reviewResult)) return;
    if (reviewResult === 'CHANGES_REQUESTED' && !reviewComment.trim()) {
      setActionMessage({ type: 'error', text: 'A comment is required when requesting changes.' });
      return;
    }
    const resultingStatus = reviewResult === 'PASSED' ? 'PENDING_MANAGER_APPROVAL' : 'CHANGES_REQUESTED';
    runAction('review', 'staff-review', resultingStatus, { result: reviewResult, comment: reviewComment.trim() || undefined });
  }

  return (
    <section className="documentation-panel staff-review-queue" aria-labelledby="staff-review-queue-heading">
      <div className="staff-review-heading">
        <div>
          <h3 id="staff-review-queue-heading">Staff Review Queue</h3>
          <p className="documentation-hint">Workflows available to your authenticated account are provided by the Backend.</p>
        </div>
        {queueOpen ? (
          <div className="documentation-actions">
            <button type="button" className="documentation-secondary-button" onClick={refreshQueue} disabled={isLoadingQueue || !userId}>
              {isLoadingQueue ? 'Refreshing...' : 'Refresh queue'}
            </button>
            <button type="button" className="documentation-secondary-button" onClick={() => setQueueOpen(false)}>Hide queue</button>
          </div>
        ) : (
          <button type="button" className="documentation-primary-button" onClick={() => {
            setQueueOpen(true);
            refreshQueue();
          }} disabled={!userId}>
            Open Staff Review Queue
          </button>
        )}
      </div>

      {!userId && <p className="documentation-empty" role="status">Sign in to load the Staff review queue.</p>}
      {userId && !queueOpen && <p className="documentation-hint">Open the queue when you need to review assigned workflows.</p>}
      {queueOpen && (
        <>
      {isLoadingQueue && <p role="status" aria-live="polite">Loading Staff review queue...</p>}
      {!isLoadingQueue && queueError && (
        <div className="documentation-error" role="alert">
          <p>{queueError}</p>
          <button type="button" className="documentation-secondary-button" onClick={refreshQueue}>Retry queue</button>
        </div>
      )}
      {!isLoadingQueue && !queueError && queue.content.length === 0 && (
        <div className="documentation-empty" role="status">No workflows are currently available in your Staff review queue.</div>
      )}
      {!isLoadingQueue && !queueError && queue.totalPages > 1 && (
        <div className="documentation-actions" role="group" aria-label="Staff review queue pagination">
          <button type="button" className="documentation-secondary-button" disabled={queue.first || pageIndex === 0}
            onClick={() => setPageIndex((value) => Math.max(0, value - 1))}>Previous</button>
          <span role="status">Page {queue.page + 1} of {queue.totalPages} · {queue.totalElements} workflows</span>
          <button type="button" className="documentation-secondary-button" disabled={queue.last}
            onClick={() => setPageIndex((value) => Math.min(queue.totalPages - 1, value + 1))}>Next</button>
        </div>
      )}
      {reviewOutcome && (
        <section className="staff-review-outcome" aria-label="Submitted Staff review result">
          <h4>Review submitted</h4>
          <p><strong>Document:</strong> {reviewOutcome.documentTitle || 'Untitled document'}</p>
          <p><strong>Result:</strong> {reviewOutcome.staffReviewResult}</p>
          <p><strong>Workflow status:</strong> {reviewOutcome.status}</p>
          {reviewOutcome.staffComment && <p><strong>Comment:</strong> {reviewOutcome.staffComment}</p>}
        </section>
      )}

      {queueOpen && !queueError && queue.content.length > 0 && (
        <div className="staff-review-layout">
          <div className="staff-review-list" aria-label="Staff review queue items">
            {queue.content.map((item) => (
              <button type="button" key={item.id}
                className={`suggestion-review-card ${String(item.id) === selectedId ? 'active' : ''}`}
                aria-pressed={String(item.id) === selectedId}
                onClick={() => { setActionMessage(null); setSelectedId(String(item.id)); }}>
                <strong>{item.documentTitle || 'Untitled document'}</strong>
                <span>Repository: Not included in workflow response</span>
                <span>Workflow: {item.status || 'Status unavailable'}</span>
                <span>Reviewer: {item.reviewerUserId || 'Unclaimed'}</span>
                <time dateTime={item.updatedAt || item.createdAt || undefined}>
                  Updated: {formatTimestamp(item.updatedAt || item.createdAt)}
                </time>
              </button>
            ))}
          </div>

          <div className="staff-review-detail" aria-label="Staff review detail">
            {!selectedId && <p className="documentation-empty" role="status">Select a workflow to review.</p>}
            {detailLoading && <p role="status" aria-live="polite">Loading workflow details...</p>}
            {detailError && <div role="alert" className="documentation-error"><p>{detailError}</p>
              <button type="button" className="documentation-secondary-button" onClick={refreshQueue}>Refresh queue and retry</button>
            </div>}
            {selectedWorkflow && !detailLoading && (
              <>
                <h4>{selectedWorkflow.documentTitle || 'Untitled document'}</h4>
                <dl className="staff-review-metadata">
                  <div><dt>Workflow status</dt><dd>{selectedWorkflow.status}</dd></div>
                  <div><dt>Repository</dt><dd>{detail.evidence?.source_snapshot?.repository_full_name || 'Unavailable in workflow metadata'}</dd></div>
                  <div><dt>Created</dt><dd>{formatTimestamp(selectedWorkflow.createdAt)}</dd></div>
                  <div><dt>Last updated</dt><dd>{formatTimestamp(selectedWorkflow.updatedAt)}</dd></div>
                  <div><dt>Claim</dt><dd>{selectedWorkflow.reviewerUserId ? `Claimed by ${selectedWorkflow.reviewerUserId}` : 'Unclaimed'}</dd></div>
                  <div><dt>Submitted version</dt><dd>{selectedWorkflow.submittedDocumentVersion || detail.content?.version || 'Not provided'}</dd></div>
                </dl>
                {detail.contentError && <p role="alert" className="documentation-error">{detail.contentError}</p>}
                <h5>Document content</h5>
                {detail.content && <pre className="staff-review-content">{detail.content.content}</pre>}

                {selectedWorkflow.staffComment && (
                  <section className="staff-review-comments">
                    <h5>Previous review comment</h5><p>{selectedWorkflow.staffComment}</p>
                  </section>
                )}
                {selectedWorkflow.managerComment && (
                  <section className="staff-review-comments">
                    <h5>Manager comment</h5><p>{selectedWorkflow.managerComment}</p>
                  </section>
                )}

                {detail.comparisonError && <p role="alert" className="documentation-error">{detail.comparisonError}</p>}
                {detail.comparison && (
                  <section>
                    <h5>AI suggestion comparison</h5>
                    <div className="suggestion-version-grid">
                      <article className="documentation-version-card"><h6>Current approved content</h6>
                        <pre>{detail.comparison.approved_version?.content || 'No previously approved version.'}</pre></article>
                      <article className="documentation-version-card"><h6>AI proposed content</h6>
                        <pre>{detail.comparison.pending_version?.content || 'No proposed content was returned.'}</pre></article>
                    </div>
                    <DiffView diff={detail.comparison.diff} />
                  </section>
                )}
                {detail.evidenceError && <p role="alert" className="documentation-error">{detail.evidenceError}</p>}
                {detail.evidence && (
                  <section>
                    <h5>Review evidence</h5>
                    {detail.evidence.source_snapshot && <p className="documentation-hint">
                      Source: {detail.evidence.source_snapshot.repository_full_name || 'Unknown repository'} / {detail.evidence.source_snapshot.branch || 'unknown branch'} @ {detail.evidence.source_snapshot.commit_sha?.slice(0, 12) || 'unknown commit'}
                    </p>}
                    {detail.evidence.source_verification && <p className="documentation-hint">
                      Source verification: {detail.evidence.source_verification.status} · {detail.evidence.source_verification.message}
                    </p>}
                    <Evidence report={detail.evidence} />
                  </section>
                )}

                {selectedWorkflow.status === 'PENDING_STAFF_REVIEW' && (
                  <button type="button" className="documentation-primary-button" disabled={Boolean(action)}
                    onClick={() => runAction('claim', 'claim', 'STAFF_REVIEWING')}>
                    {action === 'claim' ? 'Claiming...' : 'Claim review'}
                  </button>
                )}
                {assignedToMe && (
                  <>
                    <button type="button" className="documentation-secondary-button" disabled={Boolean(action)}
                      onClick={() => runAction('release', 'release', 'PENDING_STAFF_REVIEW')}>
                      {action === 'release' ? 'Releasing...' : 'Release claim'}
                    </button>
                    <form className="staff-review-form" onSubmit={submitReview}>
                      <h5>Submit Staff review</h5>
                      <label htmlFor="staff-review-result">Decision</label>
                      <select id="staff-review-result" value={reviewResult} required
                        onChange={(event) => setReviewResult(event.target.value)}>
                        <option value="">Select a decision</option>
                        <option value="PASSED">Passed</option>
                        <option value="CHANGES_REQUESTED">Request changes</option>
                      </select>
                      <label htmlFor="staff-review-comment">Review comment</label>
                      <textarea id="staff-review-comment" value={reviewComment} maxLength={2000}
                        required={reviewResult === 'CHANGES_REQUESTED'}
                        onChange={(event) => setReviewComment(event.target.value)} />
                      <p className="documentation-hint">A comment is required when requesting changes. Maximum 2,000 characters.</p>
                      <button type="submit" className="documentation-primary-button" disabled={Boolean(action) || !reviewResult}>
                        {action === 'review' ? 'Submitting review...' : 'Submit review'}
                      </button>
                    </form>
                  </>
                )}
              </>
            )}
            {actionMessage && <p role={actionMessage.type === 'success' ? 'status' : 'alert'}
              className={actionMessage.type === 'success' ? 'documentation-notice' : 'documentation-error'}>{actionMessage.text}</p>}
          </div>
        </div>
      )}
        </>
      )}
    </section>
  );
}
