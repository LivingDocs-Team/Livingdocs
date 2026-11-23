import { useEffect, useState } from 'react';
import { githubApi } from './githubApi';

const SCOPES = ['REPOSITORY', 'MODULE', 'DOCUMENT'];
const LABELS = { REPOSITORY: 'Repository', MODULE: 'Module', DOCUMENT: 'Document' };
const BASE_RULE = { scope: 'REPOSITORY', target: '', onCommit: true, onPullRequest: true };

// pathFor lets the oversight screen use its own route; by default the repository owner's route is used.
export default function AutoUpdatePolicyEditor({ repository, pathFor }) {
  const [rules, setRules] = useState(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const path = pathFor ? pathFor(repository.id)
    : `/api/repositories/${encodeURIComponent(repository.id)}/auto-update-policies`;

  useEffect(() => {
    let active = true;
    githubApi(path)
      .then((data) => { if (active) setRules(data); })
      .catch((failure) => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, [path]);

  function change(index, delta) {
    setRules((previous) => previous.map((rule, row) => row === index ? { ...rule, ...delta } : rule));
    setStatus('');
  }

  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setStatus('');
    try {
      const saved = await githubApi(path, { method: 'PUT', body: rules });
      setRules(saved);
      setStatus('Auto-update policies saved.');
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Auto-update policies" className="sync-details">
      <h3>Auto-update policies</h3>
      <p>Document rules take priority over module and repository rules. Both triggers are enabled by default.</p>
      {error && <p role="alert">{error}</p>}
      {status && <p role="status">{status}</p>}
      {rules === null ? (!error && <p role="status">Loading policies…</p>) : (
        <form onSubmit={save}>
          {rules.map((rule, index) => (
            <fieldset key={index} disabled={busy}>
              <legend>{LABELS[rule.scope]} policy</legend>
              <label>
                Scope
                <select value={rule.scope} onChange={(event) => change(index, { scope: event.target.value, target: '' })}>
                  {SCOPES.map((scope) => <option key={scope} value={scope}>{LABELS[scope]}</option>)}
                </select>
              </label>
              {rule.scope !== 'REPOSITORY' && (
                <label>
                  {rule.scope === 'MODULE' ? 'Module path' : 'Document identifier'}
                  <input type="text" required maxLength={rule.scope === 'MODULE' ? 500 : 32} value={rule.target}
                    placeholder={rule.scope === 'MODULE' ? 'src/main' : undefined}
                    pattern={rule.scope === 'DOCUMENT' ? '[0-9a-f]{32}' : undefined}
                    onChange={(event) => change(index, { target: event.target.value })} />
                </label>
              )}
              <label>
                <input type="checkbox" checked={rule.onCommit}
                  onChange={(event) => change(index, { onCommit: event.target.checked })} />
                Default-branch push
              </label>
              <label>
                <input type="checkbox" checked={rule.onPullRequest}
                  onChange={(event) => change(index, { onPullRequest: event.target.checked })} />
                Pull request
              </label>
              <button type="button" onClick={() => {
                setRules((previous) => previous.filter((_, row) => row !== index));
                setStatus('');
              }}>Remove rule</button>
            </fieldset>
          ))}
          <div className="sync-actions">
            <button type="button" disabled={busy || rules.length >= 100} onClick={() => {
              setRules((previous) => [...previous, previous.some((rule) => rule.scope === 'REPOSITORY')
                ? { ...BASE_RULE, scope: 'MODULE' } : BASE_RULE]);
              setStatus('');
            }}>Add rule</button>
            <button type="submit" disabled={busy}>Save policies</button>
          </div>
        </form>
      )}
    </section>
  );
}
