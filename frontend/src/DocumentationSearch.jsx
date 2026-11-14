import { useEffect, useState } from 'react';
import { githubApi } from './githubApi';

export default function DocumentationSearch({ userId }) {
  const workspaceId = userId ? `ws-${userId}` : '';
  const [repositories, setRepositories] = useState([]);
  const [repositoryId, setRepositoryId] = useState('');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [loadingRepositories, setLoadingRepositories] = useState(Boolean(userId));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!userId) return undefined;
    let cancelled = false;
    githubApi(`/api/workspaces/${encodeURIComponent(workspaceId)}/repositories`, { userId })
      .then((items) => {
        if (cancelled) return;
        setRepositories(items || []);
        setRepositoryId((current) => items?.some((item) => String(item.id) === current)
          ? current : String(items?.[0]?.id || ''));
      })
      .catch((requestError) => { if (!cancelled) setError(requestError.message || 'Could not load repositories.'); })
      .finally(() => { if (!cancelled) setLoadingRepositories(false); });
    return () => { cancelled = true; };
  }, [userId, workspaceId]);

  async function handleSearch(event) {
    event.preventDefault();
    const trimmed = query.trim();
    setError('');
    setResults([]);
    setHasSearched(true);
    if (!trimmed) { setError('Enter a search term.'); return; }
    if (trimmed.length > 200) { setError('Search terms must be 200 characters or fewer.'); return; }
    if (!repositoryId) { setError('Add a repository to your workspace before searching.'); return; }
    setLoading(true);
    try {
      const data = await githubApi(`/api/repositories/${encodeURIComponent(repositoryId)}/documentation/search?q=${encodeURIComponent(trimmed)}`, { userId });
      setResults(data.results || []);
    } catch (requestError) {
      setError(requestError.message || 'Search failed. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="login-card documentation-search-page" aria-labelledby="documentation-search-title">
      <h1 id="documentation-search-title">Documentation Search</h1>
      <p className="subtitle">Search repository documentation and jump to its linked source code.</p>
      <form className="documentation-search-form" onSubmit={handleSearch}>
        <label htmlFor="search-repository">Repository</label>
        <select id="search-repository" value={repositoryId} onChange={(event) => { setRepositoryId(event.target.value); setResults([]); setHasSearched(false); setError(''); }} disabled={loadingRepositories || !repositories.length}>
          {repositories.length === 0 && <option value="">No workspace repositories</option>}
          {repositories.map((repository) => <option key={repository.id} value={repository.id}>{repository.fullName}</option>)}
        </select>
        <label htmlFor="documentation-query">Search terms</label>
        <div className="documentation-search-input-row">
          <input id="documentation-query" type="search" value={query} maxLength={200} onChange={(event) => setQuery(event.target.value)} placeholder="Search docs, symbols, endpoints…" />
          <button type="submit" disabled={loading || loadingRepositories}>{loading ? 'Searching…' : 'Search'}</button>
        </div>
      </form>
      {loadingRepositories && <p className="documentation-hint" role="status">Loading repositories…</p>}
      {loading && <p className="documentation-hint" role="status">Searching the selected repository…</p>}
      {error && <p className="documentation-error" role="alert">{error}</p>}
      {hasSearched && !loading && !error && results.length === 0 && <div className="documentation-empty"><h2>No results found</h2><p>Try a different term or select another repository.</p></div>}
      {results.length > 0 && <section className="documentation-search-results" aria-live="polite" aria-label={`${results.length} search results`}>
        <h2>{results.length} result{results.length === 1 ? '' : 's'}</h2>
        {results.map((result) => <article className="documentation-search-result" key={result.id}>
          <div className="documentation-search-result-heading">
            <span className={`documentation-search-kind kind-${result.type}`}>{result.type === 'code' ? 'Code entity' : 'Documentation'}</span>
            <span>{result.repositoryName} · {result.language || 'Source'}</span>
          </div>
          <h3>{result.title}</h3>
          {result.type === 'documentation'
            ? <p>{result.summary}</p>
            : <pre><code>{result.summary}</code></pre>}
          <div className="documentation-search-result-actions">
            <span>{result.path}{result.line ? `:${result.line}` : ''}</span>
            {result.url && <a href={result.url} target="_blank" rel="noopener noreferrer">View source ↗</a>}
          </div>
        </article>)}
      </section>}
    </section>
  );
}



