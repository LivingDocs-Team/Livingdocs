import { useEffect, useState } from 'react';
import { githubApi } from './githubApi';

// LD-68: Pull Requests and commits received for one workspace repository (screen "PR & Commit List").

function pullRequestState(pr) {
  if (pr.merged) return { className: 'synced', label: 'Merged' };
  if (pr.state === 'closed') return { className: 'not-synced', label: 'Closed' };
  return { className: 'syncing', label: 'Open' };
}

function firstLine(message) {
  return String(message || '').split('\n')[0];
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString() : '';
}

export default function RepositoryActivity({ repository, userId }) {
  const [pullRequests, setPullRequests] = useState([]);
  const [commits, setCommits] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      githubApi(`/api/repositories/${repository.id}/pull-requests`, { userId }),
      githubApi(`/api/repositories/${repository.id}/commits`, { userId }),
    ])
      .then(([pullRequestList, commitList]) => {
        if (cancelled) return;
        setPullRequests(pullRequestList || []);
        setCommits(commitList || []);
      })
      .catch((requestError) => {
        if (!cancelled) setError(requestError.message || 'Could not load pull requests and commits.');
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [repository.id, userId]);

  return (
    <section className="repository-activity" aria-label={`Pull requests and commits of ${repository.fullName}`}>
      {isLoading && <p role="status">Loading pull requests and commits…</p>}
      {error && <p className="sync-error" role="alert">{error}</p>}
      {!isLoading && !error && (
        <>
          <h3>Pull requests ({pullRequests.length})</h3>
          {pullRequests.length === 0 ? (
            <p className="activity-empty">No pull requests received yet.</p>
          ) : (
            <ul className="activity-list">
              {pullRequests.map((pr) => {
                const state = pullRequestState(pr);
                return (
                  <li key={`pr-${pr.number}`}>
                    <a href={pr.htmlUrl} target="_blank" rel="noreferrer">#{pr.number} {pr.title}</a>
                    <span className={`sync-status sync-${state.className}`}>{state.label}</span>
                    <span className="activity-meta">
                      {pr.headRef} → {pr.baseRef}
                      {pr.authorLogin && ` · ${pr.authorLogin}`}
                      {pr.updatedAt && ` · updated ${formatTime(pr.updatedAt)}`}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}

          <h3>Commits ({commits.length})</h3>
          {commits.length === 0 ? (
            <p className="activity-empty">No commits received yet.</p>
          ) : (
            <ul className="activity-list">
              {commits.map((commit) => (
                <li key={`commit-${commit.sha}`}>
                  <code>{commit.sha.slice(0, 7)}</code>
                  <a href={commit.htmlUrl} target="_blank" rel="noreferrer">{firstLine(commit.message)}</a>
                  <span className="activity-meta">
                    {commit.branch}
                    {(commit.authorLogin || commit.authorName) && ` · ${commit.authorLogin || commit.authorName}`}
                    {commit.committedAt && ` · ${formatTime(commit.committedAt)}`}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      <p className="sync-last-time">Pull requests and commits arrive through the GitHub webhook and on every sync.</p>
    </section>
  );
}



