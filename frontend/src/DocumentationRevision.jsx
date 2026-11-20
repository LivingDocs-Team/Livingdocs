import { useEffect, useState } from 'react';
import { githubApi } from './githubApi';
import Can from './rbac/Can';

function revisionError(error) {
  if (error?.status === 401) return 'Your session expired. Sign in again to continue.';
  if (error?.status === 403 || error?.status === 404) return 'This revision is unavailable to your account.';
  if (error?.status === 409) return 'The document or workflow changed. Reload the revision before continuing.';
  return error?.message || 'The revision could not be completed. Reload to check the saved version.';
}

export default function DocumentationRevision({ userId, workflowId, onSubmitted }) {
  const [data, setData] = useState(null);
  const [draft, setDraft] = useState('');
  const [note, setNote] = useState('');
  const [reload, setReload] = useState(0);
  const [loadedReload, setLoadedReload] = useState(-1);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [action, setAction] = useState('');
  const prefix = `/api/document-workflows/${encodeURIComponent(workflowId)}`;
  const loading = loadedReload !== reload;

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      githubApi(prefix, { userId }),
      githubApi(`${prefix}/document`, { userId }),
      githubApi(`${prefix}/change-requests`, { userId }),
      githubApi(`${prefix}/comments`, { userId }),
    ]).then(([workflow, document, requests, comments]) => {
      if (cancelled) return;
      if (String(workflow?.id) !== String(workflowId) || String(workflow.ownerUserId) !== String(userId)
          || workflow.status !== 'CHANGES_REQUESTED') {
        throw new Error('This workflow is no longer awaiting your revision.');
      }
      if (document?.documentId !== workflow.documentId || !Number.isInteger(document.version)
          || document.version < 1 || typeof document.content !== 'string'
          || !Array.isArray(requests) || !Array.isArray(comments)) {
        throw new Error('The revision response was incomplete. Reload before editing.');
      }
      setData({ workflow, document, requests, comments });
      setDraft(document.content);
      setNote('');
      setError('');
      setNotice('');
    }).catch((requestError) => {
      if (!cancelled) {
        setData(null);
        setError(revisionError(requestError));
      }
    }).finally(() => { if (!cancelled) setLoadedReload(reload); });
    return () => { cancelled = true; };
  }, [prefix, userId, workflowId, reload]);

  const editable = !loading && data?.workflow.status === 'CHANGES_REQUESTED' && !action;
  const dirty = data && draft !== data.document.content;
  const canResubmit = editable && !dirty
    && data.document.version > data.workflow.submittedDocumentVersion;

  async function saveRevision(event) {
    event.preventDefault();
    if (!editable || !dirty || !draft.trim()) return;
    setAction('save');
    setError('');
    setNotice('');
    try {
      const response = await githubApi(`${prefix}/document`, {
        method: 'PUT', userId,
        body: { content: draft, note: note.trim() || undefined, expectedVersion: data.document.version },
      });
      if (String(response?.id) !== String(workflowId) || response.status !== 'CHANGES_REQUESTED') {
        throw new Error('The save response was incomplete. Reload to verify the saved version.');
      }
      const document = await githubApi(`${prefix}/document`, { userId });
      if (document?.documentId !== data.workflow.documentId || !Number.isInteger(document.version)
          || document.version <= data.document.version
          || document.content !== draft) {
        throw new Error('The saved document could not be confirmed. Reload before continuing.');
      }
      setData((current) => ({ ...current, workflow: response, document }));
      setNote('');
      setNotice(`Revision saved as version ${document.version}.`);
    } catch (requestError) {
      setError(revisionError(requestError));
    } finally {
      setAction('');
    }
  }

  async function resubmit() {
    if (!canResubmit) return;
    setAction('submit');
    setError('');
    setNotice('');
    try {
      const response = await githubApi(`${prefix}/submit`, {
        method: 'POST', userId, body: { expectedVersion: data.document.version },
      });
      if (String(response?.id) !== String(workflowId) || response.status !== 'PENDING_STAFF_REVIEW'
          || response.submittedDocumentVersion !== data.document.version) {
        throw new Error('The submission could not be confirmed. Reload to verify the workflow status.');
      }
      setData((current) => ({ ...current, workflow: response }));
      onSubmitted(`Version ${response.submittedDocumentVersion} submitted for Staff review.`);
    } catch (requestError) {
      setError(revisionError(requestError));
    } finally {
      setAction('');
    }
  }

  return (
    <section className="documentation-panel" aria-label="Revise requested changes">
      <h3>Revise requested changes</h3>
      {loading && <p role="status">Loading revision and feedback…</p>}
      {error && <p role="alert" className="documentation-error">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <button type="button" disabled={Boolean(action) || loading}
        onClick={() => {
          if (!dirty || window.confirm('Discard unsaved revision edits and reload?')) {
            setReload((value) => value + 1);
          }
        }}>Reload revision</button>
      {!loading && data && (
        <>
          <p>Editing version {data.document.version} · Last submitted version {data.workflow.submittedDocumentVersion}</p>
          <section aria-label="Revision feedback">
            <h4>Requested changes</h4>
            {data.requests.map((request) => (
              <article key={request.id}>
                <p>Staff {request.actorUserId} · {request.documentVersion
                  ? `Version ${request.documentVersion}` : 'Version unavailable'}</p>
                <p>{request.comment}</p>
              </article>
            ))}
            <h4>Review comments</h4>
            {data.comments.map((comment) => (
              <article key={comment.id}>
                <p>Staff {comment.actorUserId} · Version {comment.documentVersion}</p>
                {comment.section && <blockquote>{comment.section.quote}</blockquote>}
                <p>{comment.comment}</p>
              </article>
            ))}
          </section>
          <Can screen="documentation" action="U">
            <form className="staff-review-form" onSubmit={saveRevision}>
              <label htmlFor="revision-content">Revised document Markdown</label>
              <textarea id="revision-content" className="documentation-editor" rows={18} required maxLength={2000000}
                value={draft} onChange={(event) => setDraft(event.target.value)} disabled={Boolean(action)} />
              <label htmlFor="revision-note">Revision note</label>
              <textarea id="revision-note" maxLength={1000} value={note}
                onChange={(event) => setNote(event.target.value)} disabled={Boolean(action)} />
              <button type="submit" disabled={!editable || !dirty || !draft.trim()}>
                {action === 'save' ? 'Saving revision…' : 'Save revision'}
              </button>
            </form>
          </Can>
          <Can screen="workflowSubmission" action="C">
            <button type="button" onClick={resubmit} disabled={!canResubmit}>
              {action === 'submit' ? 'Submitting revision…' : 'Resubmit for review'}
            </button>
          </Can>
        </>
      )}
    </section>
  );
}
