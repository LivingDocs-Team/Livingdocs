import { useEffect, useMemo, useState } from 'react';
import { githubApi } from './githubApi';
import PageFrame from './rbac/PageFrame';
import { hrefFor } from './rbac/hashRoute.js';
import './InsightScreens.css';

function percent(documented, total) {
  return total > 0 ? Math.round((documented / total) * 100) : 0;
}

/** Coverage Gaps (matrix row #8): the code entities of a repository that no documentation is linked to. */
export default function CoverageGaps({ userId }) {
  const workspaceId = userId ? `ws-${userId}` : '';
  const [repositories, setRepositories] = useState([]);
  const [repositoryId, setRepositoryId] = useState('');
  const [loadingRepositories, setLoadingRepositories] = useState(Boolean(userId));
  const [repositoriesError, setRepositoriesError] = useState('');
  const [result, setResult] = useState(null); // { repositoryId, data } of the last finished request
  const [failure, setFailure] = useState(null); // { repositoryId, message }
  const [typeFilter, setTypeFilter] = useState('all');
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!userId) return undefined;
    let cancelled = false;
    githubApi(`/api/workspaces/${encodeURIComponent(workspaceId)}/repositories`, { userId })
      .then((items) => {
        if (cancelled) return;
        const list = Array.isArray(items) ? items : [];
        setRepositories(list);
        setRepositoryId((current) => (list.some((item) => String(item.id) === current)
          ? current : String(list[0]?.id || '')));
      })
      .catch((error) => { if (!cancelled) setRepositoriesError(error.message || 'Could not load repositories.'); })
      .finally(() => { if (!cancelled) setLoadingRepositories(false); });
    return () => { cancelled = true; };
  }, [userId, workspaceId]);

  useEffect(() => {
    if (!repositoryId || !userId) return undefined;
    let cancelled = false;
    githubApi(`/api/repositories/${encodeURIComponent(repositoryId)}/coverage-gaps`, { userId })
      .then((data) => {
        if (cancelled) return;
        if (!data || !Array.isArray(data.gaps)) throw new Error('The coverage response was not valid.');
        setResult({ repositoryId, data });
        setFailure(null);
      })
      .catch((error) => {
        if (!cancelled) setFailure({ repositoryId, message: error.message || 'Could not load coverage gaps.' });
      });
    return () => { cancelled = true; };
  }, [repositoryId, userId, reload]);

  const current = result && result.repositoryId === repositoryId ? result.data : null;
  const error = failure && failure.repositoryId === repositoryId ? failure.message : '';
  const loading = Boolean(repositoryId) && !current && !error;

  const types = useMemo(() => [...new Set((current?.gaps || []).map((gap) => gap.entityType))].sort(), [current]);
  const visible = useMemo(
    () => (current?.gaps || []).filter((gap) => typeFilter === 'all' || gap.entityType === typeFilter),
    [current, typeFilter],
  );
  const byFile = useMemo(() => {
    const groups = new Map();
    visible.forEach((gap) => groups.set(gap.path, [...(groups.get(gap.path) || []), gap]));
    return [...groups.entries()];
  }, [visible]);
  const coverage = current ? percent(current.documentedEntities, current.totalEntities) : 0;

  function selectRepository(value) {
    setRepositoryId(value);
    setTypeFilter('all');
  }

  return (
    <PageFrame
      title="Coverage Gaps"
      titleId="coverage-gaps-title"
      className="documentation-page insight-page"
      subtitle="Code that no documentation covers yet, so you know what to document next."
      actions={<a className="page-action" href={hrefFor('/documentation/documents')}>Generate documentation</a>}
    >
      <label htmlFor="coverage-repository">Repository</label>
      <select id="coverage-repository" value={repositoryId} disabled={loadingRepositories || repositories.length === 0}
        onChange={(event) => selectRepository(event.target.value)}>
        {repositories.length === 0 && <option value="">No workspace repositories</option>}
        {repositories.map((repository) => <option key={repository.id} value={repository.id}>{repository.fullName}</option>)}
      </select>

      {loadingRepositories && <p role="status">Loading repositories…</p>}
      {repositoriesError && <p className="documentation-error" role="alert">{repositoriesError}</p>}
      {!loadingRepositories && !repositoriesError && repositories.length === 0 && (
        <div className="documentation-empty">
          <h2>No repositories yet</h2>
          <p>Add and synchronize a repository first, then its coverage appears here.</p>
        </div>
      )}
      {loading && <p role="status">Checking which code is documented…</p>}
      {error && (
        <div role="alert" className="documentation-error">
          <p>{error}</p>
          <button type="button" onClick={() => { setFailure(null); setReload((value) => value + 1); }}>Retry</button>
        </div>
      )}

      {current && (
        <>
          <section className="insight-summary" aria-label="Coverage summary">
            <p className="insight-figure"><strong>{coverage}%</strong> documented</p>
            <progress max={100} value={coverage} aria-label="Documentation coverage" />
            <p>{current.documentedEntities} of {current.totalEntities} code entities have linked documentation.</p>
          </section>

          {current.totalEntities === 0 && (
            <div className="documentation-empty">
              <h2>No analyzed code</h2>
              <p>Synchronize the repository and generate documentation to analyze its code.</p>
            </div>
          )}
          {current.totalEntities > 0 && current.gaps.length === 0 && (
            <div className="documentation-empty">
              <h2>No coverage gaps</h2>
              <p>Every analyzed code entity has linked documentation.</p>
            </div>
          )}
          {current.gaps.length > 0 && (
            <section aria-label="Undocumented code">
              <label htmlFor="coverage-type">Type</label>
              <select id="coverage-type" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
                <option value="all">All types</option>
                {types.map((type) => <option key={type} value={type}>{type}</option>)}
              </select>
              <h2>{visible.length} undocumented {visible.length === 1 ? 'entity' : 'entities'}</h2>
              {byFile.map(([path, gaps]) => (
                <article key={path} className="insight-group">
                  <h3>{path}</h3>
                  <ul>
                    {gaps.map((gap) => (
                      <li key={gap.id}>
                        <span className="insight-tag">{gap.entityType}</span> {gap.name}
                        {gap.lineStart ? (
                          <small> · line {gap.lineStart}{gap.lineEnd && gap.lineEnd !== gap.lineStart ? `–${gap.lineEnd}` : ''}</small>
                        ) : null}
                        {gap.sourceUrl && <> <a href={gap.sourceUrl} target="_blank" rel="noreferrer">View source</a></>}
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </section>
          )}
        </>
      )}
    </PageFrame>
  );
}
