import { useEffect, useState } from 'react';
import AutoUpdatePolicyEditor from './AutoUpdatePolicyEditor';
import { formatTime, words } from './formatters';
import { githubApi } from './githubApi';
import PageFrame from './rbac/PageFrame';
import './InsightScreens.css';

function useOversightRepositories(userId) {
  const [state, setState] = useState({ ready: false, repositories: [], error: '' });
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!userId) return undefined;
    let cancelled = false;
    githubApi('/api/oversight/repositories', { userId })
      .then((items) => {
        if (cancelled) return;
        if (!Array.isArray(items)) throw new Error('The repository list was not valid.');
        setState({ ready: true, repositories: items, error: '' });
      })
      .catch((error) => {
        if (!cancelled) setState({ ready: true, repositories: [], error: error.message || 'Could not load repositories.' });
      });
    return () => { cancelled = true; };
  }, [userId, reload]);
  return { ...state, retry: () => { setState((current) => ({ ...current, ready: false })); setReload((value) => value + 1); } };
}

function Activity({ repositoryId, userId }) {
  const [state, setState] = useState({ key: '', pullRequests: [], commits: [], error: '' });
  const [reload, setReload] = useState(0);
  const key = `${repositoryId}:${reload}`;
  useEffect(() => {
    let cancelled = false;
    const base = `/api/oversight/repositories/${encodeURIComponent(repositoryId)}`;
    Promise.all([githubApi(`${base}/pull-requests`, { userId }), githubApi(`${base}/commits`, { userId })])
      .then(([pullRequests, commits]) => {
        if (cancelled) return;
        if (!Array.isArray(pullRequests) || !Array.isArray(commits)) throw new Error('The activity response was not valid.');
        setState({ key, pullRequests, commits, error: '' });
      })
      .catch((error) => {
        if (!cancelled) setState({ key, pullRequests: [], commits: [], error: error.message || 'Could not load the activity.' });
      });
    return () => { cancelled = true; };
  }, [repositoryId, userId, key]);

  if (state.key !== key) return <p role="status">Loading pull requests and commits…</p>;
  if (state.error) {
    return (
      <div role="alert" className="documentation-error">
        <p>{state.error}</p>
        <button type="button" onClick={() => setReload((value) => value + 1)}>Retry</button>
      </div>
    );
  }
  return (
    <>
      <h2>Pull requests ({state.pullRequests.length})</h2>
      {state.pullRequests.length === 0 ? <p className="documentation-hint">No pull requests received.</p> : (
        <ul className="insight-rows" aria-label="Pull requests">
          {state.pullRequests.map((pr) => (
            <li key={pr.number}>
              <a href={pr.htmlUrl} target="_blank" rel="noreferrer">#{pr.number} {pr.title}</a>
              <span className="insight-tag">{pr.merged ? 'merged' : pr.state}</span>
              <small>{pr.authorLogin} · {pr.headRef} → {pr.baseRef} · {formatTime(pr.updatedAt)}</small>
            </li>
          ))}
        </ul>
      )}
      <h2>Commits ({state.commits.length})</h2>
      {state.commits.length === 0 ? <p className="documentation-hint">No commits received.</p> : (
        <ul className="insight-rows" aria-label="Commits">
          {state.commits.map((commit) => (
            <li key={commit.sha}>
              <a href={commit.htmlUrl} target="_blank" rel="noreferrer">{commit.sha.slice(0, 7)} {String(commit.message).split('\n')[0]}</a>
              <span className="insight-tag">{commit.branch}</span>
              <small>{commit.authorLogin || commit.authorName} · {formatTime(commit.committedAt)}</small>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/**
 * Pull Requests & Commits (#7, read only) and Drift Policies & Thresholds (#17) for the Technical Lead, across
 * every repository. Drift policies are the auto-update rules that decide which changes refresh which documents.
 */
export default function OversightRepositories({ userId, node }) {
  const drift = node?.key === 'drift-policies';
  const list = useOversightRepositories(userId);
  const [chosen, setChosen] = useState('');
  const repositoryId = list.repositories.some((item) => item.id === chosen) ? chosen : list.repositories[0]?.id || '';
  const repository = list.repositories.find((item) => item.id === repositoryId);

  return (
    <PageFrame
      title={drift ? 'Drift Policies & Thresholds' : 'Pull Requests & Commits'}
      titleId="oversight-repositories-title"
      className="documentation-page insight-page"
      subtitle={drift
        ? 'Which commits and pull requests refresh which documents, for any repository.'
        : 'The pull requests and commits received for any repository.'}
    >
      {!list.ready && <p role="status">Loading repositories…</p>}
      {list.ready && list.error && (
        <div role="alert" className="documentation-error">
          <p>{list.error}</p>
          <button type="button" onClick={list.retry}>Retry</button>
        </div>
      )}
      {list.ready && !list.error && list.repositories.length === 0 && (
        <div className="documentation-empty">
          <h2>No repositories yet</h2>
          <p>Repositories appear here once someone connects them.</p>
        </div>
      )}
      {repository && (
        <>
          <label htmlFor="oversight-repository">Repository</label>
          <select id="oversight-repository" value={repositoryId} onChange={(event) => setChosen(event.target.value)}>
            {list.repositories.map((item) => (
              <option key={item.id} value={item.id}>{item.fullName} · {words(item.status)}</option>
            ))}
          </select>
          {drift
            ? <AutoUpdatePolicyEditor key={repositoryId} repository={repository}
                pathFor={(id) => `/api/oversight/repositories/${encodeURIComponent(id)}/drift-policies`} />
            : <Activity key={repositoryId} repositoryId={repositoryId} userId={userId} />}
        </>
      )}
    </PageFrame>
  );
}
