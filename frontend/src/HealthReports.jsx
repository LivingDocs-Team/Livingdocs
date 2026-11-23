import { useEffect, useMemo, useState } from 'react';
import { formatTime, words } from './formatters';
import { githubApi } from './githubApi';
import Can from './rbac/Can';
import PageFrame from './rbac/PageFrame';
import './InsightScreens.css';

function download(filename, type, text) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function csvCell(value) {
  const text = String(value ?? '');
  // a spreadsheet would run a cell that starts with = + - @ as a formula
  const safe = /^[=+\-@]/.test(text) ? `'${text}` : text;
  return /[",\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

function toCsv(health) {
  const labels = new Map(health.nodes.map((node) => [node.id, node.label]));
  const rows = [['section', 'name', 'value']];
  Object.entries(health.counts).forEach(([name, value]) => rows.push(['counts', name, value]));
  Object.entries(health.repositoriesByStatus).forEach(([name, value]) => rows.push(['repositories', name, value]));
  Object.entries(health.workflowsByStatus).forEach(([name, value]) => rows.push(['workflows', name, value]));
  health.edges.forEach((edge) => rows.push(['dependency', `${labels.get(edge.from)} -> ${labels.get(edge.to)}`, edge.entities]));
  return rows.map((row) => row.map(csvCell).join(',')).join('\n');
}

/** Health Metrics, Dependency Graph & Reports (matrix row #23): installation-wide counts and the doc-to-code graph. */
export default function HealthReports({ userId }) {
  const [state, setState] = useState({ ready: false, health: null, error: '' });
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!userId) return undefined;
    let cancelled = false;
    githubApi('/api/oversight/health', { userId })
      .then((health) => {
        if (cancelled) return;
        if (!health || !health.counts || !Array.isArray(health.nodes) || !Array.isArray(health.edges)) {
          throw new Error('The health report was not valid.');
        }
        setState({ ready: true, health, error: '' });
      })
      .catch((error) => {
        if (!cancelled) setState({ ready: true, health: null, error: error.message || 'Could not load the health report.' });
      });
    return () => { cancelled = true; };
  }, [userId, reload]);

  const { health } = state;
  const graph = useMemo(() => {
    if (!health) return [];
    const labels = new Map(health.nodes.map((node) => [node.id, node.label]));
    const byDocument = new Map();
    health.edges.forEach((edge) => {
      byDocument.set(edge.from, [...(byDocument.get(edge.from) || []), { file: labels.get(edge.to), entities: edge.entities }]);
    });
    return [...byDocument.entries()].map(([id, files]) => ({ id, label: labels.get(id), files }));
  }, [health]);

  return (
    <PageFrame
      title="Health Metrics, Dependency Graph & Reports"
      titleId="health-reports-title"
      className="documentation-page insight-page"
      subtitle="How much of the code is documented, where reviews stand, and which documents describe which files."
      actions={health && (
        <Can screen="healthReports" action="E">
          <button type="button" className="page-action"
            onClick={() => download('livingdocs-health.json', 'application/json', JSON.stringify(health, null, 2))}>
            Export JSON
          </button>
          <button type="button" className="page-action"
            onClick={() => download('livingdocs-health.csv', 'text/csv', toCsv(health))}>
            Export CSV
          </button>
        </Can>
      )}
    >
      {!state.ready && <p role="status">Loading the health report…</p>}
      {state.ready && state.error && (
        <div role="alert" className="documentation-error">
          <p>{state.error}</p>
          <button type="button" onClick={() => { setState({ ready: false, health: null, error: '' }); setReload((value) => value + 1); }}>Retry</button>
        </div>
      )}
      {health && (
        <>
          <p>Generated {formatTime(health.generatedAt)}</p>
          <section className="insight-summary" aria-label="Documentation coverage">
            <p className="insight-figure"><strong>{health.counts.coveragePercent}%</strong> of code entities documented</p>
            <progress max={100} value={health.counts.coveragePercent} aria-label="Documentation coverage" />
            <p>{health.counts.documentedEntities} of {health.counts.codeEntities} code entities have linked documentation.</p>
          </section>
          <ul className="insight-counts" aria-label="Totals">
            <li><strong>{health.counts.repositories}</strong> repositories</li>
            <li><strong>{health.counts.documents}</strong> documents</li>
            <li><strong>{health.counts.codeEntities}</strong> code entities</li>
          </ul>

          <h2>Repositories by status</h2>
          <ul className="insight-counts" aria-label="Repositories by status">
            {Object.entries(health.repositoriesByStatus).map(([status, count]) => (
              <li key={status}><strong>{count}</strong> {words(status)}</li>
            ))}
          </ul>
          <h2>Workflows by status</h2>
          <ul className="insight-counts" aria-label="Workflows by status">
            {Object.entries(health.workflowsByStatus).map(([status, count]) => (
              <li key={status}><strong>{count}</strong> {words(status)}</li>
            ))}
          </ul>

          <h2>Dependency graph</h2>
          {graph.length === 0 ? (
            <p className="documentation-hint">No document is linked to code yet.</p>
          ) : (
            <div aria-label="Dependency graph">
              {health.graphTruncated && (
                <p className="documentation-hint">Showing the strongest {health.edges.length} links only.</p>
              )}
              {graph.map((document) => (
                <details key={document.id} className="insight-group">
                  <summary>{document.label} <span className="insight-tag">{document.files.length} files</span></summary>
                  <ul>
                    {document.files.map((file) => (
                      <li key={file.file}>{file.file} <small>· {file.entities} code {file.entities === 1 ? 'entity' : 'entities'}</small></li>
                    ))}
                  </ul>
                </details>
              ))}
            </div>
          )}
        </>
      )}
    </PageFrame>
  );
}
