import { useCallback, useEffect, useRef, useState } from 'react';
import { githubApi } from './githubApi';
import Can from './rbac/Can';

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
  const [editedContent, setEditedContent] = useState(null);
  const [commentDraft, setCommentDraft] = useState('');
  const [selectedPassage, setSelectedPassage] = useState(null);
  const contentRef = useRef(null);

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
        const totalPages = result?.totalPages ?? (content.length ? 1 : 0);
        if (pageIndex > 0 && pageIndex >= totalPages) {
          setPageIndex(Math.max(0, totalPages - 1));
          return;
        }
        setQueue({
          content,
          page: result?.page ?? 0,
          size: result?.size ?? 20,
          totalElements: result?.totalElements ?? content.length,
          totalPages,
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
      githubApi(`${prefix}/comments`, { userId }),
      githubApi(`${prefix}/change-requests`, { userId }),
    ]).then(async ([workflowResult, contentResult, commentsResult, changesResult]) => {
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
      setDetail({ workflow, content,
        changeRequests: changesResult.status === 'fulfilled' ? changesResult.value : [],
        changesError: changesResult.status === 'rejected'
          ? errorMessage(changesResult.reason, 'load change requests') : '',
        comments: commentsResult.status === 'fulfilled' ? commentsResult.value : [],
        commentsError: commentsResult.status === 'rejected'
          ? errorMessage(commentsResult.reason, 'load review comments') : '',
        contentError: contentResult.status === 'rejected'
        ? errorMessage(contentResult.reason, 'view document content') : '', comparison, evidence, comparisonError, evidenceError });
      setReviewResult('');
      setReviewComment(workflow?.staffComment || '');
      setEditedContent(null);
      setCommentDraft('');
      setSelectedPassage(null);
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

  function selectPassage() {
    if (!assignedToMe || action) return;
    const selection = window.getSelection();
    const content = contentRef.current;
    if (!selection || selection.rangeCount !== 1 || selection.isCollapsed || !content) return;
    const range = selection.getRangeAt(0);
    if (!content.contains(range.startContainer) || !content.contains(range.endContainer)) return;
    const quote = range.toString();
    if (!quote.trim() || quote.length > 4000) {
      setSelectedPassage(null);
      setActionMessage({ type: 'error', text: 'Select a passage of 1 to 4,000 characters.' });
      return;
    }
    const before = range.cloneRange();
    before.selectNodeContents(content);
    before.setEnd(range.startContainer, range.startOffset);
    const startOffset = before.toString().length;
    setSelectedPassage({ startOffset, endOffset: startOffset + quote.length, quote });
  }

  async function submitComment(event) {
    event.preventDefault();
    if (!commentDraft.trim() || action || !assignedToMe) return;
    const workflowId = selectedId;
    setAction('comment');
    setActionMessage(null);
    try {
      const comment = await githubApi(`/api/document-workflows/${encodeURIComponent(workflowId)}/comments`, {
        method: 'POST', userId,
        body: { comment: commentDraft.trim(), documentVersion: selectedWorkflow.submittedDocumentVersion,
          ...(selectedPassage ? { section: selectedPassage } : {}) },
      });
      if (!comment?.id || String(comment.workflowId) !== workflowId) {
        throw new Error('The response did not confirm the saved comment. Refresh to verify.');
      }
      setDetail((current) => String(current?.workflow.id) === workflowId
        ? { ...current, comments: [...current.comments, comment] } : current);
      setCommentDraft('');
      setSelectedPassage(null);
      setActionMessage({ type: 'success', text: 'Comment added.' });
    } catch (error) {
      setActionMessage({ type: 'error', text: errorMessage(error, 'add a review comment') });
    } finally {
      setAction('');
    }
  }

  function submitReview(event) {
    event.preventDefault();
    if (!['PASSED', 'CHANGES_REQUESTED'].includes(reviewResult)) return;
    const comment = reviewComment.trim();
    const edit = editedContent !== null && editedContent !== detail.content?.content
      ? { content: editedContent, expectedVersion: selectedWorkflow.submittedDocumentVersion, note: comment }
      : undefined;
    if ((reviewResult === 'CHANGES_REQUESTED' || edit) && !comment) {
      setActionMessage({ type: 'error', text: 'Add a comment to explain the edit or requested changes.' });
      return;
    }
    const resultingStatus = reviewResult === 'PASSED' ? 'PENDING_MANAGER_APPROVAL' : 'CHANGES_REQUESTED';
    runAction('review', 'staff-review', resultingStatus, { result: reviewResult, comment: comment || undefined, edit });
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
            <button type="button" className="documentation-secondary-button" onClick={refreshQueue} disabled={isLoadingQueue || !userId || Boolean(action)}>
              {isLoadingQueue ? 'Refreshing...' : 'Refresh queue'}
            </button>
            <button type="button" className="documentation-secondary-button" disabled={Boolean(action)} onClick={() => setQueueOpen(false)}>Hide queue</button>
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
                disabled={Boolean(action)}
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
                {detail.content && <pre ref={contentRef} className="staff-review-content"
                  tabIndex={0} onMouseUp={selectPassage} onKeyUp={selectPassage}>{detail.content.content}</pre>}

                <section className="staff-review-comments" aria-label="Review comments">
                  <h5>Review comments</h5>
                  {detail.commentsError && <p role="alert">{detail.commentsError}</p>}
                  {detail.comments.map((comment) => (
                    <article key={comment.id}>
                      <p>Staff {comment.actorUserId} · Version {comment.documentVersion} · {formatTimestamp(comment.createdAt)}</p>
                      {comment.section && <blockquote aria-label="Referenced passage">{comment.section.quote}</blockquote>}
                      <p>{comment.comment}</p>
                    </article>
                  ))}
                  {assignedToMe && (
                    <Can screen="staffReview" action="A">
                      <form onSubmit={submitComment}>
                        <p>Select a passage in the document above to give feedback on that section.</p>
                        {selectedPassage && (
                          <div>
                            <blockquote aria-label="Selected passage">{selectedPassage.quote}</blockquote>
                            <button type="button" disabled={Boolean(action)}
                              onClick={() => setSelectedPassage(null)}>Clear passage</button>
                          </div>
                        )}
                        <label htmlFor="independent-review-comment">Add review comment</label>
                        <textarea id="independent-review-comment" required maxLength={2000}
                          value={commentDraft} onChange={(event) => setCommentDraft(event.target.value)}
                          disabled={Boolean(action)} />
                        <button type="submit" disabled={Boolean(action) || !commentDraft.trim()}>Add comment</button>
                      </form>
                    </Can>
                  )}
                </section>

                <section className="staff-review-comments" aria-label="Requested changes">
                  <h5>Requested changes</h5>
                  {detail.changesError && <p role="alert">{detail.changesError}</p>}
                  {detail.changeRequests.map((request) => (
                    <article key={request.id}>
                      <p>Staff {request.actorUserId} · {request.documentVersion
                        ? `Version ${request.documentVersion}` : 'Version unavailable'} · {formatTimestamp(request.createdAt)}</p>
                      <p>{request.comment}</p>
                      {request.relatedComments.map((comment) => (
                        <div key={comment.id}>
                          {comment.section && <blockquote>{comment.section.quote}</blockquote>}
                          <p>{comment.comment}</p>
                        </div>
                      ))}
                    </article>
                  ))}
                </section>

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
                    {detail.evidence.template_sections?.length > 0 && (
                      <p className="documentation-hint">
                        Template {detail.evidence.template_name || detail.evidence.template_id}
                        {' · v'}{detail.evidence.template_version}
                        {' · Sections: '}{detail.evidence.template_sections.join(', ')}
                      </p>
                    )}
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
                  <Can screen="staffReview" action="U">
                    <button type="button" className="documentation-primary-button" disabled={Boolean(action)}
                      onClick={() => runAction('claim', 'claim', 'STAFF_REVIEWING')}>
                      {action === 'claim' ? 'Claiming...' : 'Claim review'}
                    </button>
                  </Can>
                )}
                {assignedToMe && (
                  <Can screen="staffReview" action="A">
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
                      <textarea id="staff-review-comment" value={reviewComment} maxLength={editedContent === null ? 2000 : 1000}
                        required={reviewResult === 'CHANGES_REQUESTED'}
                        onChange={(event) => setReviewComment(event.target.value)} />
                      {detail.content?.content && (editedContent === null ? (
                        <button type="button" onClick={() => setEditedContent(detail.content.content)}>Edit draft</button>
                      ) : (
                        <>
                          <label htmlFor="staff-draft-content">Draft content</label>
                          <textarea id="staff-draft-content" value={editedContent} required maxLength={2000000}
                            onChange={(event) => setEditedContent(event.target.value)} />
                          <button type="button" onClick={() => setEditedContent(null)}>Discard edits</button>
                        </>
                      ))}
                      <p className="documentation-hint">A comment is required when requesting changes. Maximum 2,000 characters.</p>
                      <button type="submit" className="documentation-primary-button" disabled={Boolean(action) || !reviewResult}>
                        {action === 'review' ? 'Submitting review...' : 'Submit review'}
                      </button>
                    </form>
                  </Can>
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
