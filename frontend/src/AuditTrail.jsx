import { useEffect, useState } from 'react';
import { formatTime, words } from './formatters';
import { githubApi } from './githubApi';
import './InsightScreens.css';

function AuditEvent({ event }) {
  return (
    <li className="changelog-entry">
      <h3>
        {words(event.action) || 'Event'}
        {event.documentVersion != null && <span className="insight-tag">version {event.documentVersion}</span>}
      </h3>
      <p>
        {formatTime(event.createdAt)} · by {event.actorUserId || 'unknown'}
        {event.actorRole ? ` (${words(event.actorRole)})` : ''}
      </p>
      {(event.previousStatus || event.newStatus) && (
        <p>Status: {words(event.previousStatus) || 'none'} → {words(event.newStatus) || 'none'}</p>
      )}
      {event.newReviewerUserId && event.newReviewerUserId !== event.previousReviewerUserId && (
        <p>Reviewer: {event.newReviewerUserId}</p>
      )}
      {event.comment && <blockquote>{event.comment}</blockquote>}
    </li>
  );
}

/** The recorded events of one workflow, in the order they happened. `only` keeps the listed actions. */
export default function AuditTrail({ workflowId, userId, only }) {
  const [state, setState] = useState({ key: '', events: [], error: '' });
  const [reload, setReload] = useState(0);
  const key = `${workflowId}:${reload}`;

  useEffect(() => {
    if (!workflowId || !userId) return undefined;
    let cancelled = false;
    githubApi(`/api/document-workflows/${encodeURIComponent(workflowId)}/history`, { userId })
      .then((events) => {
        if (cancelled) return;
        if (!Array.isArray(events)) throw new Error('The audit trail was not valid.');
        setState({ key, events, error: '' });
      })
      .catch((error) => {
        if (!cancelled) setState({ key, events: [], error: error.message || 'Could not load the audit trail.' });
      });
    return () => { cancelled = true; };
  }, [workflowId, userId, key]);

  if (!workflowId) return null;
  if (state.key !== key) return <p role="status">Loading the audit trail…</p>;
  if (state.error) {
    return (
      <div role="alert" className="documentation-error">
        <p>{state.error}</p>
        <button type="button" onClick={() => setReload((value) => value + 1)}>Retry</button>
      </div>
    );
  }
  const events = only ? state.events.filter((event) => only.includes(event.action)) : state.events;
  if (events.length === 0) {
    return <div className="documentation-empty"><h2>No events recorded</h2></div>;
  }
  return (
    <ol className="changelog" aria-label="Audit trail">
      {events.map((event) => <AuditEvent key={event.id} event={event} />)}
    </ol>
  );
}
