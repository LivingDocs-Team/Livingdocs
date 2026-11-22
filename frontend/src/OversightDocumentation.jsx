import { useEffect, useMemo, useState } from 'react';
import { formatTime } from './formatters';
import { githubApi } from './githubApi';
import PageFrame from './rbac/PageFrame';
import './InsightScreens.css';

function DocumentBody({ id, userId }) {
  const [state, setState] = useState({ key: '', markdown: '', error: '' });
  const [reload, setReload] = useState(0);
  const key = `${id}:${reload}`;
  useEffect(() => {
    let cancelled = false;
    githubApi(`/api/oversight/documentation/${encodeURIComponent(id)}`, { userId })
      .then((document) => {
        if (cancelled) return;
        if (!document || typeof document.markdown !== 'string') throw new Error('The document was not valid.');
        setState({ key, markdown: document.markdown, error: '' });
      })
      .catch((error) => {
        if (!cancelled) setState({ key, markdown: '', error: error.message || 'Could not load the document.' });
      });
    return () => { cancelled = true; };
  }, [id, userId, key]);

  if (state.key !== key) return <p role="status">Loading the document…</p>;
  if (state.error) {
    return (
      <div role="alert" className="documentation-error">
        <p>{state.error}</p>
        <button type="button" onClick={() => setReload((value) => value + 1)}>Retry</button>
      </div>
    );
  }
  return <pre className="oversight-document" aria-label="Document content">{state.markdown}</pre>;
}

/** Documentation (matrix row #8, read only): every generated document of every repository. */
export default function OversightDocumentation({ userId }) {
  const [state, setState] = useState({ ready: false, documents: [], error: '' });
  const [reload, setReload] = useState(0);
  const [filter, setFilter] = useState('');
  const [chosen, setChosen] = useState('');

  useEffect(() => {
    if (!userId) return undefined;
    let cancelled = false;
    githubApi('/api/oversight/documentation', { userId })
      .then((items) => {
        if (cancelled) return;
        if (!Array.isArray(items)) throw new Error('The document list was not valid.');
        setState({ ready: true, documents: items, error: '' });
      })
      .catch((error) => {
        if (!cancelled) setState({ ready: true, documents: [], error: error.message || 'Could not load documents.' });
      });
    return () => { cancelled = true; };
  }, [userId, reload]);

  const visible = useMemo(() => {
    const term = filter.trim().toLowerCase();
    return state.documents.filter((item) => !term
      || `${item.title} ${item.repositoryName || ''}`.toLowerCase().includes(term));
  }, [state.documents, filter]);
  const selected = visible.find((item) => item.id === chosen) || visible[0] || null;

  return (
    <PageFrame title="Documentation" titleId="oversight-documentation-title" className="documentation-page insight-page"
      subtitle="The documents generated for every repository. View only.">
      {!state.ready && <p role="status">Loading documents…</p>}
      {state.ready && state.error && (
        <div role="alert" className="documentation-error">
          <p>{state.error}</p>
          <button type="button" onClick={() => { setState({ ready: false, documents: [], error: '' }); setReload((value) => value + 1); }}>Retry</button>
        </div>
      )}
      {state.ready && !state.error && state.documents.length === 0 && (
        <div className="documentation-empty">
          <h2>No documents yet</h2>
          <p>Generated documents appear here.</p>
        </div>
      )}
      {state.documents.length > 0 && (
        <>
          <label htmlFor="oversight-doc-filter">Filter by title or repository</label>
          <input id="oversight-doc-filter" type="search" value={filter} maxLength={100}
            onChange={(event) => setFilter(event.target.value)} />
          {visible.length === 0 ? <p className="documentation-hint">No document matches the filter.</p> : (
            <>
              <label htmlFor="oversight-document">Document ({visible.length})</label>
              <select id="oversight-document" value={selected?.id || ''} onChange={(event) => setChosen(event.target.value)}>
                {visible.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title}{item.repositoryName ? ` · ${item.repositoryName}` : ''}
                  </option>
                ))}
              </select>
              {selected && (
                <>
                  <p>
                    {selected.repositoryName || 'Unknown repository'} · created {formatTime(selected.createdAt)}
                    {selected.sourceCommit ? ` · commit ${selected.sourceCommit.slice(0, 7)}` : ''}
                  </p>
                  <DocumentBody key={selected.id} id={selected.id} userId={userId} />
                </>
              )}
            </>
          )}
        </>
      )}
    </PageFrame>
  );
}
