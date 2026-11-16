import { useEffect, useState } from 'react';
import { githubApi } from './githubApi';

function requestMessage(error, resource) {
  if (error?.status === 401) return 'Your session has expired. Sign in again to review this suggestion.';
  if (error?.status === 403) return `You do not have permission to view ${resource}.`;
  if (error?.status === 404) return `The ${resource} could not be found or is not available to this account.`;
  if (error?.status === 409) return 'The workflow or document version changed. Reload the suggestion and try again.';
  return error?.message || `Could not load ${resource}.`;
}

function timestamp(value) {
  if (!value) return 'Not provided';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function changeCounts(diff) {
  const lines = String(diff || '').split(/\r?\n/);
  return {
    added: lines.filter((line) => line.startsWith('+') && !line.startsWith('+++')).length,
    removed: lines.filter((line) => line.startsWith('-') && !line.startsWith('---')).length,
  };
}

function DiffLines({ diff }) {
  if (!diff) return <p className="documentation-empty">No line diff was returned for this comparison.</p>;
  return (
    <pre className="suggestion-diff" aria-label="Backend unified content diff">
      {diff.split(/\r?\n/).map((line, index) => {
        const kind = line.startsWith('+++') || line.startsWith('---') || line.startsWith('@@')
          ? 'meta'
          : line.startsWith('+') ? 'added' : line.startsWith('-') ? 'removed' : 'context';
        return <span className={`suggestion-diff-line suggestion-diff-${kind}`} key={`${index}-${line}`}>{line || ' '}{'\n'}</span>;
      })}
    </pre>
  );
}

function EvidenceList({ report }) {
  const files = Array.isArray(report?.files) ? report.files : [];
  const hasEvidence = files.some((file) => (file.entities || []).some((entity) => (entity.evidence || []).length)
    || (file.context_used || []).length);
  if (!hasEvidence) return <p className="documentation-empty">No AI review evidence was returned for this version.</p>;

  return (
    <div className="suggestion-evidence-list">
      {files.map((file) => (
        <article className="documentation-version-card" key={file.path}>
          <h5><code>{file.path}</code></h5>
          <p>Generation status: {file.status || 'Not provided'}</p>
          {(file.entities || []).map((entity) => (
            <section key={`${file.path}-${entity.kind}-${entity.name}`}>
              <strong>{entity.kind}: {entity.name}</strong>
              {entity.level && <span> · Confidence: {entity.level}</span>}
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

export default function DocumentationSuggestionReview({
  workflows = [],
  selectedWorkflowId,
  onSelectWorkflow,
  userId,
  repositories = [],
  documents = [],
  currentRepositoryId,
  isLoadingWorkflows = false,
  workflowsError = '',
}) {
  const workflow = workflows.find((item) => String(item.id) === String(selectedWorkflowId));
  const [loadedSuggestion, setLoadedSuggestion] = useState(null);
  const [reloadCount, setReloadCount] = useState(0);
  const [editingWorkflowId, setEditingWorkflowId] = useState('');
  const [draftContent, setDraftContent] = useState('');
  const [editNote, setEditNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [editResult, setEditResult] = useState(null);

  useEffect(() => {
    if (!workflow || !userId) return undefined;
    let cancelled = false;
    const assignedReviewer = workflow.status === 'STAFF_REVIEWING'
      && String(workflow.reviewerUserId) === String(userId);
    const requestList = [
      ['document', `/api/document-workflows/${encodeURIComponent(workflow.id)}/document`],
    ];
    if (assignedReviewer) {
      requestList.push(['comparison', `/api/document-workflows/${encodeURIComponent(workflow.id)}/review-comparison`]);
      requestList.push(['evidence', `/api/document-workflows/${encodeURIComponent(workflow.id)}/review-evidence`]);
    }

    Promise.allSettled(requestList.map(([, path]) => githubApi(path, { userId })))
      .then((results) => {
        if (cancelled) return;
        const values = {};
        const errors = {};
        results.forEach((result, index) => {
          const [name] = requestList[index];
          if (result.status === 'fulfilled') values[name] = result.value;
          else errors[name] = requestMessage(result.reason, name === 'document' ? 'workflow content' : name.replace(/([A-Z])/g, ' $1').toLowerCase());
        });
        if (!values.document || typeof values.document.content !== 'string') {
          errors.document = errors.document || 'The workflow content response was invalid.';
        }
        const comparison = values.comparison;
        if (comparison && !comparison.pending_version) {
          errors.comparison = 'The backend did not return a pending suggestion version.';
          delete values.comparison;
        }
        setLoadedSuggestion({ workflowId: String(workflow.id), values, errors });
        setDraftContent(comparison?.pending_version?.content || values.document?.content || '');
      });

    return () => { cancelled = true; };
  }, [workflow, userId, reloadCount]);

  const suggestion = loadedSuggestion?.workflowId === String(workflow?.id) ? loadedSuggestion : null;
  const data = suggestion?.values || {};
  const errors = suggestion?.errors || {};
  const isAssignedReviewer = workflow?.status === 'STAFF_REVIEWING'
    && String(workflow?.reviewerUserId) === String(userId);
  const canEdit = workflow && workflow.status === 'CHANGES_REQUESTED'
    && String(workflow.ownerUserId) === String(userId);
  const comparison = data.comparison;
  const pendingVersion = comparison?.pending_version;
  const approvedVersion = comparison?.approved_version;
  const documentIsInCurrentRepository = documents.some((item) => String(item.id) === String(workflow?.documentId));
  const repositoryId = documents.find((item) => String(item.id) === String(workflow?.documentId))?.repositoryId;
  const repository = data.evidence?.source_snapshot?.repository_full_name
    || repositories.find((item) => String(item.id) === String(repositoryId))?.fullName
    || (documentIsInCurrentRepository
      ? repositories.find((item) => String(item.id) === String(currentRepositoryId))?.fullName : '');
  const counts = changeCounts(comparison?.diff);
  const isEditing = editingWorkflowId === String(workflow?.id);

  async function saveEdit(event) {
    event.preventDefault();
    if (!workflow || saving || !draftContent.trim()) return;
    setSaving(true);
    setEditResult(null);
    try {
      const updated = await githubApi(`/api/document-workflows/${encodeURIComponent(workflow.id)}/document`, {
        method: 'PUT', userId, body: { content: draftContent, note: editNote || undefined },
      });
      if (String(updated?.id) !== String(workflow.id) || updated?.status !== workflow.status) {
        throw new Error('The edit response did not confirm the expected workflow state.');
      }
      setEditResult({ type: 'success', text: 'The edited proposal was saved by the backend.' });
      setEditingWorkflowId('');
      setEditNote('');
      setReloadCount((count) => count + 1);
    } catch (error) {
      setEditResult({ type: 'error', text: requestMessage(error, 'the edited document') });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="documentation-panel suggestion-review" aria-labelledby="ai-suggestion-review-heading">
      <h3 id="ai-suggestion-review-heading">AI Suggestion Review</h3>
      <p className="documentation-hint">
        Review the backend-provided proposal and source evidence. Accept and dismiss actions are not available through the public workflow API.
      </p>

      {isLoadingWorkflows && <p role="status">Loading review suggestions...</p>}
      {!isLoadingWorkflows && workflowsError && (
        <div className="documentation-error" role="alert">{workflowsError}</div>
      )}
      {!isLoadingWorkflows && !workflowsError && workflows.length === 0 && (
        <div className="documentation-empty" role="status">No accessible review suggestions are available.</div>
      )}

      {workflows.length > 0 && (
        <div className="suggestion-review-layout">
          <div className="suggestion-review-list" aria-label="AI suggestion list">
            {workflows.map((item) => {
              const inCurrentRepository = documents.some((document) => String(document.id) === String(item.documentId));
              const repositoryName = item.repositoryFullName
                || (inCurrentRepository
                  ? repositories.find((repositoryItem) => String(repositoryItem.id) === String(currentRepositoryId))?.fullName
                  : '');
              return (
                <button
                  type="button"
                  className={`suggestion-review-card ${String(item.id) === String(selectedWorkflowId) ? 'active' : ''}`}
                  aria-pressed={String(item.id) === String(selectedWorkflowId)}
                  key={item.id}
                  onClick={() => {
                    setEditResult(null);
                    setEditingWorkflowId('');
                    onSelectWorkflow(String(item.id));
                  }}
                >
                  <strong>{item.documentTitle || 'Untitled document'}</strong>
                  <span>Repository: {repositoryName || 'Not included in workflow metadata'}</span>
                  <span>Workflow: {item.status || 'Status unavailable'}</span>
                  <span>Review: {item.staffReviewResult || item.managerDecision || item.status || 'Not reviewed'}</span>
                  <time dateTime={item.createdAt || undefined}>Created: {timestamp(item.createdAt)}</time>
                </button>
              );
            })}
          </div>

          {!workflow && <div className="documentation-empty" role="status">Select a workflow to inspect its suggestion.</div>}
          {workflow && !suggestion && <p role="status" aria-live="polite">Loading suggestion details...</p>}
          {workflow && errors.document && (
            <div className="documentation-error" role="alert">
              <p>{errors.document}</p>
              <button type="button" className="documentation-secondary-button" onClick={() => setReloadCount((count) => count + 1)}>
                Retry loading suggestion
              </button>
            </div>
          )}

          {workflow && suggestion && !errors.document && (
            <div className="suggestion-review-detail" aria-label="AI suggestion detail">
              <div className="suggestion-review-metadata">
                <span><strong>Document:</strong> {workflow.documentTitle || 'Untitled document'}</span>
                <span><strong>Repository:</strong> {repository || 'Not available to this account'}</span>
                <span><strong>Workflow status:</strong> {workflow.status}</span>
                <span><strong>Workflow created:</strong> {timestamp(workflow.createdAt)}</span>
                <span><strong>Submitted version:</strong> {workflow.submittedDocumentVersion || data.document?.version || 'Not provided'}</span>
              </div>

              {isAssignedReviewer ? (
                <>
                  <h4>Content comparison</h4>
                  {errors.comparison && <p className="documentation-error" role="alert">{errors.comparison}</p>}
                  {comparison && (
                    <>
                      <div className="suggestion-version-grid">
                        <article className="documentation-version-card">
                          <h5>Current approved content {approvedVersion ? `(v${approvedVersion.number})` : ''}</h5>
                          {approvedVersion?.created_at && <p>Version created: {timestamp(approvedVersion.created_at)}</p>}
                          <pre>{approvedVersion?.content || 'No previously approved version is available.'}</pre>
                        </article>
                        <article className="documentation-version-card">
                          <h5>AI proposed content (v{pendingVersion?.number || 'unknown'})</h5>
                          <p>Status: {pendingVersion?.status || 'Not provided'} · Origin: {pendingVersion?.origin || 'Not provided'}</p>
                          {pendingVersion?.created_at && <p>Version created: {timestamp(pendingVersion.created_at)}</p>}
                          <pre>{pendingVersion?.content || 'The backend returned no proposed content.'}</pre>
                        </article>
                      </div>
                      <div className="suggestion-change-summary" aria-label="Change summary">
                        <span>{counts.added} added line(s)</span>
                        <span>{counts.removed} removed line(s)</span>
                      </div>
                      <DiffLines diff={comparison.diff} />
                      {pendingVersion?.changes?.length > 0 && (
                        <div className="suggestion-section-changes">
                          <h5>Changed documentation sections</h5>
                          <ul>
                            {pendingVersion.changes.map((change, index) => (
                              <li key={`${change.path}-${change.action}-${index}`}>
                                <strong>{change.action}</strong> <code>{change.path}</code>
                                {change.previous_path && <span> (from <code>{change.previous_path}</code>)</span>}
                                {change.entities?.length > 0 && <span> · Entities: {change.entities.join(', ')}</span>}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </>
                  )}

                  <h4>AI evidence</h4>
                  {errors.evidence && <p className="documentation-error" role="alert">{errors.evidence}</p>}
                  {data.evidence && (
                    <>
                      {data.evidence.source_snapshot && <p className="documentation-hint">
                        Source snapshot: {data.evidence.source_snapshot.repository_full_name || 'Repository unavailable'} · branch {data.evidence.source_snapshot.branch || 'unknown'} · commit {data.evidence.source_snapshot.commit_sha?.slice(0, 12) || 'unknown'}
                      </p>}
                      {data.evidence.source_verification && <p className="documentation-hint" data-source-verification={data.evidence.source_verification.status}>
                        Source verification: {data.evidence.source_verification.status} — {data.evidence.source_verification.message}
                      </p>}
                      <EvidenceList report={data.evidence} />
                    </>
                  )}
                  {(errors.comparison || errors.evidence) && (
                    <button type="button" className="documentation-secondary-button" onClick={() => setReloadCount((count) => count + 1)}>
                      Retry loading review details
                    </button>
                  )}
                </>
              ) : (
                <div className="documentation-empty" role="status">
                  <p>Workflow document content, version {data.document?.version || 'unknown'}.</p>
                  <pre>{data.document?.content || 'No workflow content was returned.'}</pre>
                  <p>AI comparison and evidence are available only to the Staff member currently assigned to this workflow.</p>
                </div>
              )}

              {canEdit && (
                <div className="suggestion-edit">
                  <h4>Edit after requested changes</h4>
                  {!isEditing ? (
                    <button type="button" className="documentation-secondary-button" onClick={() => {
                      setDraftContent(pendingVersion?.content || data.document?.content || '');
                      setEditingWorkflowId(String(workflow.id));
                      setEditResult(null);
                    }}>Edit proposal</button>
                  ) : (
                    <form onSubmit={saveEdit}>
                      <label htmlFor="suggestion-edit-content">Document content</label>
                      <textarea id="suggestion-edit-content" value={draftContent} maxLength={2000000} required
                        onChange={(event) => setDraftContent(event.target.value)} />
                      <label htmlFor="suggestion-edit-note">Edit note (optional)</label>
                      <input id="suggestion-edit-note" value={editNote} maxLength={1000}
                        onChange={(event) => setEditNote(event.target.value)} />
                      <div className="documentation-actions">
                        <button type="submit" className="documentation-primary-button" disabled={saving || !draftContent.trim()}>
                          {saving ? 'Saving...' : 'Save edit'}
                        </button>
                        <button type="button" className="documentation-secondary-button" disabled={saving}
                          onClick={() => setEditingWorkflowId('')}>Cancel</button>
                      </div>
                    </form>
                  )}
                  <p className="documentation-hint">Editing is available only after Staff requested changes. The document remains in its current workflow state until the backend confirms another transition.</p>
                </div>
              )}
              {editResult && <p className={editResult.type === 'success' ? 'documentation-notice' : 'documentation-error'}
                role={editResult.type === 'success' ? 'status' : 'alert'}>{editResult.text}</p>}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
