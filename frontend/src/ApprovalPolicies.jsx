import { useEffect, useState } from 'react';
import { formatTime } from './formatters';
import { githubApi } from './githubApi';
import Can from './rbac/Can';
import PageFrame from './rbac/PageFrame';
import './InsightScreens.css';

const DEFAULT_TEMPLATE = 'Publish LivingDocs document {document} v{version}';

function previewMessage(template) {
  return template.replace('{document}', 'doc-1234').replace('{version}', '3');
}

/**
 * Approval Policy and Merge Policy for Managers (matrix row #12). The approval policy decides which comments a
 * review or an approval must contain; the merge policy decides whether and how an approved document is
 * published to GitHub. Both are enforced by the workflow service.
 */
export default function ApprovalPolicies({ userId, node }) {
  const merge = node?.key === 'merge-policy';
  const type = merge ? 'merge' : 'approval';
  const [state, setState] = useState({ key: '', policy: null, error: '' });
  const [draft, setDraft] = useState(null);
  const [reload, setReload] = useState(0);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const key = `${type}:${reload}`;

  useEffect(() => {
    if (!userId) return undefined;
    let cancelled = false;
    githubApi(`/api/approval/policies/${type}`, { userId })
      .then((policy) => {
        if (cancelled) return;
        if (!policy || typeof policy.settings !== 'object' || policy.settings === null) throw new Error('The policy was not valid.');
        setState({ key, policy, error: '' });
        setDraft(policy.settings);
      })
      .catch((failure) => {
        if (!cancelled) setState({ key, policy: null, error: failure.message || 'Could not load the policy.' });
      });
    return () => { cancelled = true; };
  }, [userId, type, key]);

  const ready = state.key === key;
  const policy = ready ? state.policy : null;
  const template = draft?.commitMessageTemplate ?? DEFAULT_TEMPLATE;
  const invalidTemplate = merge && (!template.trim() || template.includes('\n'));

  async function save(event) {
    event.preventDefault();
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const saved = await githubApi(`/api/approval/policies/${type}`, { method: 'PUT', userId, body: draft });
      setState({ key, policy: saved, error: '' });
      setDraft(saved.settings);
      setMessage('Policy saved.');
    } catch (failure) {
      setError(failure.message || 'Could not save the policy.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <PageFrame
      title={merge ? 'Merge Policy' : 'Approval Policy'}
      titleId="approval-policy-title"
      className="documentation-page insight-page"
      subtitle={merge
        ? 'Whether an approved document may be published to GitHub, and the commit message it is published with.'
        : 'What every Staff review and every Manager approval must contain.'}
    >
      {!ready && <p role="status">Loading the policy…</p>}
      {ready && state.error && (
        <div role="alert" className="documentation-error">
          <p>{state.error}</p>
          <button type="button" onClick={() => setReload((value) => value + 1)}>Retry</button>
        </div>
      )}
      {policy && draft && (
        <form onSubmit={save} aria-label={merge ? 'Merge policy' : 'Approval policy'}>
          <fieldset disabled={saving}>
            {merge ? (
              <>
                <label className="insight-check">
                  <input type="checkbox" checked={Boolean(draft.allowCommitBack)}
                    onChange={(event) => setDraft({ ...draft, allowCommitBack: event.target.checked })} />
                  Allow publishing approved documents to GitHub
                </label>
                <label htmlFor="merge-template">Commit message</label>
                <input id="merge-template" value={template} maxLength={200}
                  onChange={(event) => setDraft({ ...draft, commitMessageTemplate: event.target.value })} />
                <p className="documentation-hint">Use {'{document}'} and {'{version}'}. Example: <code>{previewMessage(template)}</code></p>
              </>
            ) : (
              <>
                <label className="insight-check">
                  <input type="checkbox" checked={Boolean(draft.requireStaffComment)}
                    onChange={(event) => setDraft({ ...draft, requireStaffComment: event.target.checked })} />
                  Staff must comment on every review
                </label>
                <label className="insight-check">
                  <input type="checkbox" checked={Boolean(draft.requireManagerComment)}
                    onChange={(event) => setDraft({ ...draft, requireManagerComment: event.target.checked })} />
                  Managers must comment on every approval
                </label>
              </>
            )}
          </fieldset>
          <p className="documentation-hint">
            {policy.updatedAt ? `Last changed by ${policy.updatedBy} on ${formatTime(policy.updatedAt)}.` : 'Using the defaults.'}
          </p>
          {error && <p role="alert" className="documentation-error">{error}</p>}
          {message && <p role="status">{message}</p>}
          <Can screen="approvalPolicies" action="U">
            <button type="submit" disabled={saving || invalidTemplate}>{saving ? 'Saving…' : 'Save policy'}</button>
          </Can>
        </form>
      )}
    </PageFrame>
  );
}
