import { useEffect, useState } from 'react';
import { formatTime } from './formatters';
import { githubApi } from './githubApi';
import Can from './rbac/Can';
import PageFrame from './rbac/PageFrame';
import './InsightScreens.css';

const DAY = 24 * 60 * 60 * 1000;

function localInputValue(date) {
  const offset = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function DelegationList({ title, items, onRevoke, busy }) {
  return (
    <section aria-label={title}>
      <h2>{title}</h2>
      {items.length === 0 ? <p className="documentation-hint">None.</p> : (
        <ul className="insight-rows">
          {items.map((item) => (
            <li key={item.id}>
              <strong>{onRevoke ? `To Manager ${item.delegateUserId}` : `From Manager ${item.delegatorUserId}`}</strong>
              <span className="insight-tag">{item.state.toLowerCase()}</span>
              <small>{formatTime(item.startsAt)} → {formatTime(item.endsAt)}{item.reason ? ` · ${item.reason}` : ''}</small>
              {onRevoke && (item.state === 'ACTIVE' || item.state === 'SCHEDULED') && (
                <Can screen="managerApproval" action="U">
                  <button type="button" disabled={busy} onClick={() => onRevoke(item)}
                    aria-label={`Revoke delegation to ${item.delegateUserId}`}>Revoke</button>
                </Can>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * Approval Delegation (matrix row #11): a Manager records that another Manager covers their approvals for a
 * period. The record is visible to both Managers and can be revoked. While it is active the delegator cannot
 * make final decisions and the delegate's decisions are recorded as covering for them.
 */
export default function ApprovalDelegation({ userId }) {
  const [state, setState] = useState({ key: '', data: null, error: '' });
  const [reload, setReload] = useState(0);
  const [delegate, setDelegate] = useState('');
  const [endsAt, setEndsAt] = useState(() => localInputValue(new Date(Date.now() + 7 * DAY)));
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const key = String(reload);

  useEffect(() => {
    if (!userId) return undefined;
    let cancelled = false;
    githubApi('/api/approval/delegations', { userId })
      .then((data) => {
        if (cancelled) return;
        if (!data || !Array.isArray(data.outgoing) || !Array.isArray(data.incoming)) throw new Error('The delegation list was not valid.');
        setState({ key, data, error: '' });
      })
      .catch((failure) => {
        if (!cancelled) setState({ key, data: null, error: failure.message || 'Could not load delegations.' });
      });
    return () => { cancelled = true; };
  }, [userId, key]);

  async function create(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await githubApi('/api/approval/delegations', {
        method: 'POST', userId,
        body: { delegateUserId: delegate.trim(), reason: reason.trim(), endsAt: new Date(endsAt).toISOString() },
      });
      setDelegate('');
      setReason('');
      setMessage('Delegation saved.');
      setReload((value) => value + 1);
    } catch (failure) {
      setError(failure.message || 'Could not save the delegation.');
    } finally {
      setBusy(false);
    }
  }

  async function revoke(item) {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await githubApi(`/api/approval/delegations/${encodeURIComponent(item.id)}`, { method: 'DELETE', userId });
      setMessage('Delegation revoked.');
      setReload((value) => value + 1);
    } catch (failure) {
      setError(failure.message || 'Could not revoke the delegation.');
    } finally {
      setBusy(false);
    }
  }

  const ready = state.key === key;
  const data = ready ? state.data : null;

  return (
    <PageFrame
      title="Approval Delegation"
      titleId="approval-delegation-title"
      className="documentation-page insight-page"
      subtitle="Tell the team which Manager covers your approvals while you are away."
    >
      <Can screen="managerApproval" action="U">
        <form onSubmit={create} aria-label="New delegation">
          <label htmlFor="delegate-user">Manager user ID</label>
          <input id="delegate-user" value={delegate} maxLength={100} required
            onChange={(event) => setDelegate(event.target.value)} />
          <label htmlFor="delegate-ends">Until</label>
          <input id="delegate-ends" type="datetime-local" value={endsAt} required
            onChange={(event) => setEndsAt(event.target.value)} />
          <label htmlFor="delegate-reason">Reason (optional)</label>
          <input id="delegate-reason" value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} />
          <p className="documentation-hint">A delegation lasts at most 90 days and starts now. While it is active you cannot decide documents yourself; revoke it to take over again.</p>
          <button type="submit" disabled={busy || !delegate.trim()}>Delegate approvals</button>
        </form>
      </Can>
      {error && <p role="alert" className="documentation-error">{error}</p>}
      {message && <p role="status">{message}</p>}

      {!ready && <p role="status">Loading delegations…</p>}
      {ready && state.error && (
        <div role="alert" className="documentation-error">
          <p>{state.error}</p>
          <button type="button" onClick={() => setReload((value) => value + 1)}>Retry</button>
        </div>
      )}
      {data && (
        <>
          <DelegationList title="Delegated by you" items={data.outgoing} onRevoke={revoke} busy={busy} />
          <DelegationList title="Delegated to you" items={data.incoming} busy={busy} />
        </>
      )}
    </PageFrame>
  );
}
