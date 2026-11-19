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

// LD-122 / LD-126: documentation that one source change (LD-116) may have made outdated, with the evidence.
function AffectedDocumentation({ change }) {
  if (change.status === 'FAILED') {
    return <p className="activity-empty">Changes could not be detected: {change.errorMessage || change.errorCode}</p>;
  }
  if (!change.documentsStatus) return <p className="activity-empty">Affected documentation was not checked.</p>;
  if (change.documentsStatus === 'PENDING') return <p className="activity-empty">Checking affected documentation…</p>;
  if (change.documentsStatus === 'FAILED') {
    return (
      <p className="sync-error" role="alert">
        Affected documentation could not be checked: {change.documentsErrorMessage || change.documentsErrorCode}
      </p>
    );
  }
  const documents = change.affectedDocuments || [];
  if (documents.length === 0) return <p className="activity-empty">No documentation is affected.</p>;
  return (
    <ul className="affected-docs" aria-label={`Documentation affected by ${change.commitSha.slice(0, 7)}`}>
      {documents.map((doc) => (
        <li key={`${doc.documentId}-${doc.section}`}>
          <strong>{doc.title}</strong>
          <code>{doc.section}</code>
          <span className={`sync-status ${doc.dependency === 'DIRECT' ? 'sync-failed' : 'sync-syncing'}`}>
            {doc.dependency === 'DIRECT' ? 'Direct' : 'Dependent'}
          </span>
          <span className="activity-meta">{(doc.reasons || []).join(' · ')}</span>
          {doc.evidence?.length > 0 && (
            <ul className="impact-evidence">
              {doc.evidence.map((item) => (
                <li key={`${item.line}-${item.target}`}>
                  Line {item.line}: <code>{item.excerpt}</code>
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ul>
  );
}

export default function RepositoryActivity({ repository, userId }) {
  const [pullRequests, setPullRequests] = useState([]);
  const [commits, setCommits] = useState([]);
  const [sourceChanges, setSourceChanges] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      githubApi(`/api/repositories/${repository.id}/pull-requests`, { userId }),
      githubApi(`/api/repositories/${repository.id}/commits`, { userId }),
      githubApi(`/api/repositories/${repository.id}/source-changes`, { userId }),
    ])
      .then(([pullRequestList, commitList, sourceChangeList]) => {
        if (cancelled) return;
        setPullRequests(pullRequestList || []);
        setCommits(commitList || []);
        setSourceChanges(sourceChangeList || []);
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

          <h3>Source changes ({sourceChanges.length})</h3>
          {sourceChanges.length === 0 ? (
            <p className="activity-empty">No source changes detected yet.</p>
          ) : (
            <ul className="activity-list">
              {sourceChanges.map((change) => (
                <li key={`change-${change.id}`}>
                  <code>{change.commitSha.slice(0, 7)}</code>
                  <span>{change.trigger === 'PULL_REQUEST' ? `Pull request #${change.pullRequestNumber}` : 'Commit'}</span>
                  <span className="activity-meta">
                    {(change.files || []).length} source file(s) · {formatTime(change.createdAt)}
                  </span>
                  <AffectedDocumentation change={change} />
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
