import { useEffect, useState } from 'react';
import AuditTrail from './AuditTrail';
import DocumentVersionComparison from './DocumentVersionComparison';
import { formatTime, words } from './formatters';
import { githubApi } from './githubApi';
import PageFrame from './rbac/PageFrame';
import RollbackAction from './RollbackAction';
import useWorkflowList from './useWorkflowList';
import './InsightScreens.css';

function useVersions(workflowId, userId) {
  const [state, setState] = useState({ key: '', versions: [], error: '' });
  const [reload, setReload] = useState(0);
  const key = `${workflowId}:${reload}`;
  useEffect(() => {
    if (!workflowId || !userId) return undefined;
    let cancelled = false;
    githubApi(`/api/document-workflows/${encodeURIComponent(workflowId)}/versions`, { userId })
      .then((list) => {
        if (cancelled) return;
        if (!Array.isArray(list)) throw new Error('The version list was not valid.');
        setState({ key, versions: [...list].sort((a, b) => b.number - a.number), error: '' });
      })
      .catch((error) => {
        if (!cancelled) setState({ key, versions: [], error: error.message || 'Could not load versions.' });
      });
    return () => { cancelled = true; };
  }, [workflowId, userId, key]);
  return { ready: state.key === key, versions: state.versions, error: state.key === key ? state.error : '',
    retry: () => setReload((value) => value + 1) };
}

function VersionList({ workflowId, userId, workflow, onRolledBack }) {
  const { ready, versions, error, retry } = useVersions(workflowId, userId);
  if (!ready) return <p role="status">Loading versions…</p>;
  if (error) {
    return (
      <div role="alert" className="documentation-error">
        <p>{error}</p>
        <button type="button" onClick={retry}>Retry</button>
      </div>
    );
  }
  if (versions.length === 0) return <div className="documentation-empty"><h2>No versions recorded</h2></div>;
  return (
    <ol className="changelog" aria-label="Versions">
      {versions.map((version) => (
        <li key={version.number} className="changelog-entry">
          <h3>
            Version {version.number}
            <span className="insight-tag">{words(version.status)}</span>
            {version.restored_from != null && <span className="insight-tag">restored from {version.restored_from}</span>}
          </h3>
          <p>{words(version.origin)} · {formatTime(version.created_at)}{version.created_by ? ` · by ${version.created_by}` : ''}</p>
          {version.note && <blockquote>{version.note}</blockquote>}
          <RollbackAction userId={userId} workflow={workflow} version={version.number}
            accepted={String(version.status).toLowerCase() === 'accepted'} onDone={onRolledBack} />
        </li>
      ))}
    </ol>
  );
}

/**
 * Version History & Comparison (#18) and Document Rollback (#19) for the Technical Lead, read only.
 * On the rollback screen a Technical Lead may start a rollback; the restored version is a new proposal that
 * Staff review and a Manager approve again.
 */
export default function VersionExplorer({ userId, node }) {
  const rollback = node?.key === 'document-rollback';
  const list = useWorkflowList(userId);
  const { page } = list;
  const [notice, setNotice] = useState('');

  return (
    <PageFrame
      title={rollback ? 'Document Rollback' : 'Version History & Comparison'}
      titleId="version-explorer-title"
      className="documentation-page insight-page"
      subtitle={rollback
        ? 'Versions of a document and the rollbacks requested for it. A restored version goes back to Staff review.'
        : 'Every version of a document and the difference between any two of them.'}
    >
      {!list.ready && <p role="status">Loading documents…</p>}
      {list.ready && list.error && (
        <div role="alert" className="documentation-error">
          <p>{list.error}</p>
          <button type="button" onClick={list.retry}>Retry</button>
        </div>
      )}
      {list.ready && !list.error && list.workflows.length === 0 && (
        <div className="documentation-empty">
          <h2>No documents yet</h2>
          <p>Documents appear here once they have been submitted for review.</p>
        </div>
      )}

      {list.workflows.length > 0 && (
        <>
          <label htmlFor="version-document">Document</label>
          <select id="version-document" value={list.selectedId} onChange={(event) => list.select(event.target.value)}>
            {list.workflows.map((item) => (
              <option key={item.id} value={item.id}>
                {item.documentTitle || item.documentId || 'Untitled document'} · {words(item.status)}
              </option>
            ))}
          </select>
          {page && page.totalPages > 1 && (
            <nav className="insight-pager" aria-label="Document pages">
              <button type="button" disabled={page.first} onClick={() => list.setPageIndex((value) => value - 1)}>Previous</button>
              <span>Page {page.page + 1} of {page.totalPages}</span>
              <button type="button" disabled={page.last} onClick={() => list.setPageIndex((value) => value + 1)}>Next</button>
            </nav>
          )}
          {rollback ? (
            <>
              {notice && <p role="status">{notice}</p>}
              <h2>Versions</h2>
              <VersionList key={`v-${list.selectedId}`} workflowId={list.selectedId} userId={userId}
                workflow={list.workflows.find((item) => item.id === list.selectedId)} onRolledBack={(text) => { setNotice(text); list.retry(); }} />
              <h2>Rollback requests</h2>
              <AuditTrail key={`a-${list.selectedId}`} workflowId={list.selectedId} userId={userId}
                only={['ROLLBACK_REQUESTED']} />
            </>
          ) : (
            <DocumentVersionComparison key={list.selectedId} workflowId={list.selectedId} userId={userId} />
          )}
        </>
      )}
    </PageFrame>
  );
}
