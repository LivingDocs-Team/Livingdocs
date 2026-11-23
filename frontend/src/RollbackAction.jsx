import { useState } from 'react';
import { githubApi } from './githubApi';
import { usePermission } from './rbac/usePermission';

/**
 * "Roll back to this version" for one version of a document. The Backend turns the restored text into a
 * new proposal that goes through Staff review and Manager approval again, so this never publishes anything
 * by itself. Only an approved document can be rolled back, only to a version that was accepted (a superseded or
 * dismissed version is refused by the Backend), and not to the version that is already approved.
 */
export default function RollbackAction({ userId, workflow, version, accepted = true, onDone }) {
  const { can } = usePermission();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  if (!can('documentRollback', 'U') || !workflow || workflow.status !== 'APPROVED' || !accepted
      || workflow.submittedDocumentVersion === version) {
    return message ? <p role="status">{message}</p> : null;
  }

  async function submit(event) {
    event.preventDefault();
    if (!reason.trim()) {
      setError('A rollback reason is required.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const response = await githubApi(`/api/document-workflows/${encodeURIComponent(workflow.id)}/rollback`, {
        method: 'POST', userId, body: { sourceVersion: version, reason: reason.trim() },
      });
      if (response?.status !== 'PENDING_STAFF_REVIEW') {
        throw new Error('The Backend did not confirm the rollback. Refresh and check the document.');
      }
      setOpen(false);
      setReason('');
      const text = `Version ${version} was restored as a new proposal and sent to Staff review.`;
      setMessage(text);
      if (onDone) onDone(text);
    } catch (failure) {
      setError(failure.message || 'Could not roll back the document.');
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <>
        {message && <p role="status">{message}</p>}
        <button type="button" className="documentation-secondary-button" onClick={() => setOpen(true)}
          aria-label={`Roll back to version ${version}`}>
          Roll back to this version
        </button>
      </>
    );
  }
  return (
    <form onSubmit={submit} aria-label={`Roll back to version ${version}`}>
      <label htmlFor={`rollback-reason-${version}`}>Why roll back to version {version}?</label>
      <textarea id={`rollback-reason-${version}`} rows={3} maxLength={1000} value={reason}
        onChange={(event) => setReason(event.target.value)} />
      {error && <p role="alert" className="documentation-error">{error}</p>}
      <p className="documentation-hint">The restored version goes back to Staff review before it can be approved.</p>
      <button type="submit" disabled={busy}>{busy ? 'Requesting…' : 'Request rollback'}</button>
      <button type="button" className="documentation-secondary-button" disabled={busy}
        onClick={() => { setOpen(false); setError(''); }}>Cancel</button>
    </form>
  );
}
