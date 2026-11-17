import { Fragment, useEffect, useMemo, useState } from 'react';
import { githubApi } from './githubApi';

// LD-183 Documentation diff & comparison (UC-30, BR-44).
// DiffView shows two versions side by side: added lines (LD-186) in green, removed lines (LD-186)
// in red, modified lines (LD-187) in amber with the changed words marked. Long runs of unchanged
// lines are folded. DocumentVersionComparison lets the user choose any two saved versions of a
// workflow's document (LD-184); by default the current version is compared with the previous one.

const CONTEXT_LINES = 3;
const KIND_LABEL = { added: 'Added', removed: 'Removed', modified: 'Modified', unchanged: 'Unchanged' };
const MARKER = { added: '+', removed: '−', modified: '~', unchanged: ' ' };
const SECTION_LABEL = { added: 'added', removed: 'removed', modified: 'modified', unchanged: 'unchanged' };

function Segments({ segments, text }) {
  if (!segments?.length) return text || ' ';
  return segments.map((segment, index) => (segment.changed
    ? <mark key={index} className="diff-inline-changed">{segment.text}</mark>
    : <Fragment key={index}>{segment.text}</Fragment>));
}

function Cell({ row, side }) {
  const number = side === 'old' ? row.old_number : row.new_number;
  const text = side === 'old' ? row.old_text : row.new_text;
  if (number === null || number === undefined) {
    return <div role="cell" className="documentation-diff-line diff-empty" aria-hidden="true" />;
  }
  let kindClass = '';
  if (row.kind === 'modified') kindClass = 'diff-modified';
  else if (row.kind === 'removed' && side === 'old') kindClass = 'diff-removed';
  else if (row.kind === 'added' && side === 'new') kindClass = 'diff-added';
  return (
    <div role="cell" className={`documentation-diff-line ${kindClass}`}
      aria-label={row.kind === 'unchanged' ? undefined : `${KIND_LABEL[row.kind]} line ${number}`}>
      <span className="diff-line-number">{number}</span>
      <span className="diff-marker" aria-hidden="true">{MARKER[row.kind]}</span>
      <code className="diff-text">
        <Segments segments={side === 'old' ? row.old_segments : row.new_segments} text={text} />
      </code>
    </div>
  );
}

// Unchanged runs longer than 2 × CONTEXT_LINES are folded, keeping a few lines of context.
function foldRows(rows, expanded) {
  const items = [];
  let k = 0;
  while (k < rows.length) {
    if (rows[k].kind !== 'unchanged') {
      items.push({ row: rows[k], index: k });
      k += 1;
      continue;
    }
    let end = k;
    while (end < rows.length && rows[end].kind === 'unchanged') end += 1;
    const head = k === 0 ? 0 : CONTEXT_LINES;
    const tail = end === rows.length ? 0 : CONTEXT_LINES;
    if (expanded.has(k) || end - k <= head + tail + 1) {
      for (let i = k; i < end; i += 1) items.push({ row: rows[i], index: i });
    } else {
      for (let i = k; i < k + head; i += 1) items.push({ row: rows[i], index: i });
      items.push({ fold: k, count: end - k - head - tail });
      for (let i = end - tail; i < end; i += 1) items.push({ row: rows[i], index: i });
    }
    k = end;
  }
  return items;
}

export function DiffSummary({ diff }) {
  const stats = diff?.stats || {};
  const changedSections = (diff?.sections || []).filter((section) => section.status !== 'unchanged');
  return (
    <div className="diff-summary">
      <p role="status" aria-live="polite" className="diff-stats">
        {diff?.identical
          ? 'The two versions are identical.'
          : `${stats.added || 0} added · ${stats.removed || 0} removed · ${stats.modified || 0} modified · ${stats.unchanged || 0} unchanged lines`}
      </p>
      {changedSections.length > 0 && (
        <ul className="diff-sections" aria-label="Changed sections">
          {changedSections.map((section) => (
            <li key={section.section} className={`diff-section diff-section-${section.status}`}>
              <strong>{section.section}</strong> {SECTION_LABEL[section.status]}
              {section.status === 'modified'
                && ` (+${section.added} / −${section.removed} / ~${section.modified})`}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function DiffView({ diff, oldLabel, newLabel }) {
  const [expanded, setExpanded] = useState(() => new Set());
  const rows = useMemo(() => diff?.rows || [], [diff]);
  const items = useMemo(() => foldRows(rows, expanded), [rows, expanded]);
  if (!rows.length) {
    return <p className="documentation-empty">Both versions are empty.</p>;
  }
  return (
    <div className="documentation-diff diff-view" role="table" aria-label={`Comparison of ${oldLabel} and ${newLabel}`}>
      <div role="row" className="diff-row diff-header">
        <div role="columnheader">{oldLabel}</div>
        <div role="columnheader">{newLabel}</div>
      </div>
      {items.map((item) => (item.fold !== undefined ? (
        <div role="row" className="diff-row diff-fold" key={`fold-${item.fold}`}>
          <div role="cell">
            <button type="button" className="text-button"
              onClick={() => setExpanded((current) => new Set(current).add(item.fold))}>
              Show {item.count} unchanged line{item.count === 1 ? '' : 's'}
            </button>
          </div>
        </div>
      ) : (
        <div role="row" className={`diff-row diff-row-${item.row.kind}`} key={item.index} data-kind={item.row.kind}>
          <Cell row={item.row} side="old" />
          <Cell row={item.row} side="new" />
        </div>
      )))}
    </div>
  );
}

function versionLabel(version) {
  if (!version) return '';
  const status = version.status ? ` · ${version.status}` : '';
  return `Version ${version.number}${status}`;
}

// The parent renders it with key={workflowId}, so a new workflow starts with fresh state.
export default function DocumentVersionComparison({ workflowId, userId }) {
  const [loaded, setLoaded] = useState(null); // { versions, error } once the list has arrived
  const [fromChoice, setFromChoice] = useState(null); // null = default (the previous version)
  const [toChoice, setToChoice] = useState(null); // null = default (the current version)
  const [result, setResult] = useState({ key: '', diff: null, error: '' });

  useEffect(() => {
    if (!workflowId || !userId) return undefined;
    let cancelled = false;
    githubApi(`/api/document-workflows/${encodeURIComponent(workflowId)}/versions`, { userId })
      .then((list) => {
        if (cancelled) return;
        const versions = [...(Array.isArray(list) ? list : [])].sort((a, b) => b.number - a.number);
        setLoaded({ versions, error: '' });
      })
      .catch((requestError) => {
        if (!cancelled) setLoaded({ versions: [], error: requestError.message });
      });
    return () => { cancelled = true; };
  }, [workflowId, userId]);

  const versions = loaded?.versions || [];
  // current vs previous by default (LD-184)
  const toVersion = toChoice ?? (versions[0] ? String(versions[0].number) : '');
  const fromVersion = fromChoice ?? (versions[1] ? String(versions[1].number) : '');
  const requestKey = fromVersion && toVersion && fromVersion !== toVersion ? `${fromVersion}:${toVersion}` : '';

  useEffect(() => {
    if (!workflowId || !requestKey) return undefined;
    let cancelled = false;
    const [from, to] = requestKey.split(':');
    const query = `from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`;
    githubApi(`/api/document-workflows/${encodeURIComponent(workflowId)}/comparison?${query}`, { userId })
      .then((diff) => { if (!cancelled) setResult({ key: requestKey, diff, error: '' }); })
      .catch((requestError) => {
        if (!cancelled) setResult({ key: requestKey, diff: null, error: requestError.message });
      });
    return () => { cancelled = true; };
  }, [workflowId, userId, requestKey]);

  if (!workflowId) return null;
  const loadingVersions = loaded === null;
  const current = requestKey && result.key === requestKey ? result : null;
  const loadingDiff = Boolean(requestKey) && !current;
  const error = loaded?.error || current?.error || '';
  const diff = current?.diff || null;
  const byNumber = (value) => versions.find((version) => String(version.number) === value);

  return (
    <section className="documentation-version-comparison" aria-labelledby="version-comparison-title">
      <h3 id="version-comparison-title">Compare document versions</h3>
      {loadingVersions && <p role="status" aria-live="polite">Loading document versions…</p>}
      {!loadingVersions && !loaded.error && versions.length < 2 && (
        <div className="documentation-empty">
          <p>Create a version first to enable comparison.</p>
        </div>
      )}
      {versions.length >= 2 && (
        <div className="diff-version-pickers">
          <label htmlFor="compare-from-version">
            Older version
            <select id="compare-from-version" value={fromVersion} onChange={(event) => setFromChoice(event.target.value)}>
              <option value="">Choose a version</option>
              {versions.map((version) => (
                <option key={version.number} value={String(version.number)}>{versionLabel(version)}</option>
              ))}
            </select>
          </label>
          <button type="button" className="documentation-secondary-button" aria-label="Swap versions"
            disabled={!fromVersion || !toVersion}
            onClick={() => { setFromChoice(toVersion); setToChoice(fromVersion); }}>
            ⇄ Swap
          </button>
          <label htmlFor="compare-to-version">
            Newer version
            <select id="compare-to-version" value={toVersion} onChange={(event) => setToChoice(event.target.value)}>
              <option value="">Choose a version</option>
              {versions.map((version) => (
                <option key={version.number} value={String(version.number)}>{versionLabel(version)}</option>
              ))}
            </select>
          </label>
        </div>
      )}
      {versions.length >= 2 && (!fromVersion || !toVersion) && (
        <p className="documentation-hint">Select a version to display the comparison.</p>
      )}
      {versions.length >= 2 && fromVersion && fromVersion === toVersion && (
        <p className="documentation-hint" role="status">Select two different versions to compare.</p>
      )}
      {error && <p className="documentation-error" role="alert">{error}</p>}
      {loadingDiff && <p role="status" aria-live="polite">Comparing versions…</p>}
      {diff && (
        <>
          <DiffSummary diff={diff} />
          <DiffView
            key={requestKey}
            diff={diff}
            oldLabel={versionLabel(byNumber(fromVersion) || diff.from_version)}
            newLabel={versionLabel(byNumber(toVersion) || diff.to_version)}
          />
        </>
      )}
    </section>
  );
}
