import { useEffect, useMemo, useState } from 'react';
import { githubApi } from './githubApi';
import PageFrame from './rbac/PageFrame';
import { hrefFor } from './rbac/hashRoute.js';
import './InsightScreens.css';

const PAGE_SIZE = 50;

// Which notification preference switches each kind of message on (see NotificationPreferences).
const KINDS = {
  submitted: { preference: 'reviewRequests', title: 'Submitted for review' },
  claimed: { preference: 'reviewRequests', title: 'Review started' },
  staffReview: { preference: 'documentChanges', title: 'Staff review result' },
  managerDecision: { preference: 'documentChanges', title: 'Manager decision' },
};

function words(value) {
  return String(value || '').replace(/_/g, ' ').toLowerCase();
}

function storageKey(userId) {
  return `livingdocs.notifications.seen.${userId}`;
}

function readSeen(userId) {
  try {
    return Number(window.localStorage.getItem(storageKey(userId))) || 0;
  } catch {
    return 0;
  }
}

/** The messages a workflow record tells: submission, review start, Staff result and Manager decision. */
function notificationsFrom(workflows) {
  const items = [];
  (Array.isArray(workflows) ? workflows : []).forEach((workflow) => {
    const title = workflow.documentTitle || workflow.documentId || 'Untitled document';
    const add = (kind, at, text, comment) => {
      const time = at ? Date.parse(at) : NaN;
      if (Number.isNaN(time)) return;
      items.push({ id: `${workflow.id}:${kind}`, kind, time, at, workflow, title, text, comment: comment || '' });
    };
    add('submitted', workflow.submittedAt, `"${title}" was submitted for Staff review.`);
    if (workflow.reviewerUserId) {
      add('claimed', workflow.reviewedAt || workflow.submittedAt,
        `Staff ${workflow.reviewerUserId} took "${title}" for review.`);
    }
    if (workflow.staffReviewResult) {
      add('staffReview', workflow.reviewedAt, `Staff review of "${title}": ${words(workflow.staffReviewResult)}.`,
        workflow.staffComment);
    }
    if (workflow.managerDecision) {
      add('managerDecision', workflow.decidedAt, `Manager decision on "${title}": ${words(workflow.managerDecision)}.`,
        workflow.managerComment);
    }
  });
  return items.sort((a, b) => b.time - a.time);
}

/** Notifications (matrix row #3): the review and approval messages about the user's documents. */
export default function Notifications({ userId }) {
  const [state, setState] = useState({ key: '', workflows: [], preferences: null, error: '' });
  const [reload, setReload] = useState(0);
  const [selectedId, setSelectedId] = useState('');
  const [seenAt, setSeenAt] = useState(() => readSeen(userId));
  const [showAll, setShowAll] = useState(false);

  const requestKey = `${userId}:${reload}`;
  useEffect(() => {
    if (!userId) return undefined;
    let cancelled = false;
    Promise.all([
      githubApi(`/api/document-workflows/history-accessible?page=0&size=${PAGE_SIZE}`, { userId }),
      githubApi('/api/profile/notification-preferences').catch(() => null),
    ])
      .then(([page, preferences]) => {
        if (cancelled) return;
        if (!page || !Array.isArray(page.content)) throw new Error('The notification data was not valid.');
        setState({ key: requestKey, workflows: page.content, preferences, error: '' });
      })
      .catch((error) => {
        if (!cancelled) setState({ key: requestKey, workflows: [], preferences: null, error: error.message || 'Could not load notifications.' });
      });
    return () => { cancelled = true; };
  }, [userId, requestKey]);

  const ready = state.key === requestKey;
  const all = useMemo(() => notificationsFrom(state.workflows), [state.workflows]);
  const enabled = (item) => !state.preferences || state.preferences[KINDS[item.kind].preference] !== false;
  const items = showAll ? all : all.filter(enabled);
  const hidden = all.length - all.filter(enabled).length;
  const unread = items.filter((item) => item.time > seenAt).length;
  const selected = all.find((item) => item.id === selectedId) || null;

  function markAllRead() {
    const latest = all.reduce((max, item) => Math.max(max, item.time), Date.now());
    setSeenAt(latest);
    try {
      window.localStorage.setItem(storageKey(userId), String(latest));
    } catch {
      // the read marker is only a convenience; without storage it is kept for this page view
    }
  }

  return (
    <PageFrame
      title="Notifications"
      titleId="notifications-title"
      className="documentation-page insight-page"
      subtitle="Review and approval messages about your documents."
      actions={<a className="page-action" href={hrefFor('/account/notification-preferences')}>Notification Preferences</a>}
    >
      {!ready && <p role="status">Loading notifications…</p>}
      {ready && state.error && (
        <div role="alert" className="documentation-error">
          <p>{state.error}</p>
          <button type="button" onClick={() => setReload((value) => value + 1)}>Retry</button>
        </div>
      )}
      {ready && !state.error && (
        <>
          <div className="insight-toolbar">
            <p role="status">{unread > 0 ? `${unread} unread` : 'All caught up'}</p>
            <button type="button" onClick={markAllRead} disabled={unread === 0}>Mark all as read</button>
          </div>
          {hidden > 0 && (
            <label className="insight-check">
              <input type="checkbox" checked={showAll} onChange={(event) => setShowAll(event.target.checked)} />
              Show {hidden} message{hidden === 1 ? '' : 's'} turned off in your preferences
            </label>
          )}
          {items.length === 0 ? (
            <div className="documentation-empty">
              <h2>No notifications</h2>
              <p>Messages appear here when your documents are submitted, reviewed or decided.</p>
            </div>
          ) : (
            <ul className="notification-list" aria-label="Notifications">
              {items.map((item) => (
                <li key={item.id} className={item.time > seenAt ? 'notification is-unread' : 'notification'}>
                  <button type="button" aria-pressed={item.id === selectedId}
                    onClick={() => setSelectedId(item.id === selectedId ? '' : item.id)}>
                    <strong>{KINDS[item.kind].title}</strong>
                    <span>{item.text}</span>
                    <small>{new Date(item.time).toLocaleString()}</small>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {selected && (
            <section className="notification-details" aria-label="Notification details">
              <h2>{KINDS[selected.kind].title}</h2>
              <p>{selected.text}</p>
              <dl>
                <div><dt>Document</dt><dd>{selected.title}</dd></div>
                <div><dt>Status</dt><dd>{words(selected.workflow.status)}</dd></div>
                <div><dt>When</dt><dd>{new Date(selected.time).toLocaleString()}</dd></div>
                {selected.comment && <div><dt>Comment</dt><dd>{selected.comment}</dd></div>}
              </dl>
              <a className="page-action" href={hrefFor('/documentation/documents/feedback')}>Open review feedback</a>
            </section>
          )}
        </>
      )}
    </PageFrame>
  );
}
