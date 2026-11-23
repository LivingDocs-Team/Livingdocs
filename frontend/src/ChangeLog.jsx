import { useEffect, useState } from 'react';
import { githubApi } from './githubApi';
import PageFrame from './rbac/PageFrame';
import './InsightScreens.css';

const PAGE_SIZE = 20;

function formatTime(value) {
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleString() : 'Unknown time';
}

function label(value) {
  return String(value || '').replace(/_/g, ' ').toLowerCase();
}

function VersionEntry({ version }) {
  const changes = Array.isArray(version.changes) ? version.changes : [];
  const warnings = Array.isArray(version.warnings) ? version.warnings : [];
  return (
    <li className="changelog-entry">
      <h3>
        Version {version.number}
        <span className="insight-tag">{label(version.status)}</span>
        {version.manual && <span className="insight-tag">edited by hand</span>}
      </h3>
      <p>
        {label(version.origin) || 'Unknown origin'} · {formatTime(version.created_at)}
        {version.created_by ? ` · by ${version.created_by}` : ''}
      </p>
      {version.restored_from != null && <p>Restored from version {version.restored_from}.</p>}
      {version.base_version != null && <p>Built on version {version.base_version}.</p>}
      {version.note && <blockquote>{version.note}</blockquote>}
      {changes.length > 0 ? (
        <ul aria-label={`Changes in version ${version.number}`}>
          {changes.map((change, index) => (
            <li key={`${change.path}-${index}`}>
              <span className="insight-tag">{label(change.action)}</span> {change.path}
              {change.previous_path ? <small> (was {change.previous_path})</small> : null}
              {change.entities?.length > 0 && <small> · {change.entities.join(', ')}</small>}
            </li>
          ))}
        </ul>
      ) : (
        <p className="documentation-hint">No section changes were recorded for this version.</p>
      )}
      {warnings.length > 0 && <ul className="documentation-error">{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
    </li>
  );
}

/** Change Log (matrix row #18): what changed in each version of the documents the user can open. */
export default function ChangeLog({ userId }) {
  const [pageIndex, setPageIndex] = useState(0);
  const [workflowId, setWorkflowId] = useState('');
  const [listState, setListState] = useState({ key: '', page: null, error: '' });
  const [logState, setLogState] = useState({ key: '', versions: [], error: '' });
  const [reload, setReload] = useState(0);

  const listKey = `${userId}:${pageIndex}:${reload}`;
  useEffect(() => {
    if (!userId) return undefined;
    let cancelled = false;
    githubApi(`/api/document-workflows/history-accessible?page=${pageIndex}&size=${PAGE_SIZE}`, { userId })
      .then((page) => {
        if (cancelled) return;
        if (!page || !Array.isArray(page.content)) throw new Error('The document list was not valid.');
        setListState({ key: listKey, page, error: '' });
        setWorkflowId((current) => (page.content.some((item) => item.id === current)
          ? current : page.content[0]?.id || ''));
      })
      .catch((error) => {
        if (!cancelled) setListState({ key: listKey, page: null, error: error.message || 'Could not load documents.' });
      });
    return () => { cancelled = true; };
  }, [userId, pageIndex, listKey]);

  const logKey = `${workflowId}:${reload}`;
  useEffect(() => {
    if (!workflowId || !userId) return undefined;
    let cancelled = false;
    githubApi(`/api/document-workflows/${encodeURIComponent(workflowId)}/versions`, { userId })
      .then((list) => {
        if (cancelled) return;
        if (!Array.isArray(list)) throw new Error('The version list was not valid.');
        setLogState({ key: logKey, versions: [...list].sort((a, b) => b.number - a.number), error: '' });
      })
      .catch((error) => {
        if (!cancelled) setLogState({ key: logKey, versions: [], error: error.message || 'Could not load versions.' });
      });
    return () => { cancelled = true; };
  }, [workflowId, userId, logKey]);

  const listReady = listState.key === listKey;
  const page = listReady ? listState.page : null;
  const documents = page?.content || [];
  const listError = listReady ? listState.error : '';
  const logReady = Boolean(workflowId) && logState.key === logKey;
  const selected = documents.find((item) => item.id === workflowId);

  return (
    <PageFrame
      title="Change Log"
      titleId="change-log-title"
      className="documentation-page insight-page"
      subtitle="What changed in each version of a document, newest first."
    >
      {!listReady && <p role="status">Loading documents…</p>}
      {listError && (
        <div role="alert" className="documentation-error">
          <p>{listError}</p>
          <button type="button" onClick={() => setReload((value) => value + 1)}>Retry</button>
        </div>
      )}
      {listReady && !listError && documents.length === 0 && (
        <div className="documentation-empty">
          <h2>No documents yet</h2>
          <p>Documents you submit for review appear here with their version changes.</p>
        </div>
      )}

      {documents.length > 0 && (
        <>
          <label htmlFor="change-log-document">Document</label>
          <select id="change-log-document" value={workflowId} onChange={(event) => setWorkflowId(event.target.value)}>
            {documents.map((item) => (
              <option key={item.id} value={item.id}>
                {item.documentTitle || item.documentId || 'Untitled document'} · {label(item.status)}
              </option>
            ))}
          </select>
          {page && page.totalPages > 1 && (
            <nav className="insight-pager" aria-label="Document pages">
              <button type="button" disabled={page.first} onClick={() => setPageIndex((value) => value - 1)}>Previous</button>
              <span>Page {page.page + 1} of {page.totalPages}</span>
              <button type="button" disabled={page.last} onClick={() => setPageIndex((value) => value + 1)}>Next</button>
            </nav>
          )}

          {!logReady && <p role="status">Loading versions…</p>}
          {logReady && logState.error && (
            <div role="alert" className="documentation-error">
              <p>{logState.error}</p>
              <button type="button" onClick={() => setReload((value) => value + 1)}>Retry</button>
            </div>
          )}
          {logReady && !logState.error && logState.versions.length === 0 && (
            <div className="documentation-empty">
              <h2>No versions recorded</h2>
              <p>{selected?.documentTitle || 'This document'} has no saved versions yet.</p>
            </div>
          )}
          {logReady && logState.versions.length > 0 && (
            <ol className="changelog" aria-label="Version change log">
              {logState.versions.map((version) => <VersionEntry key={version.number} version={version} />)}
            </ol>
          )}
        </>
      )}
    </PageFrame>
  );
}
