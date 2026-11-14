import { useEffect, useMemo, useState } from 'react';
import { githubApi, githubApiText } from './githubApi';

// LD-159 Display drift severity: run a drift check for a pull request and show every finding
// with its severity level, why it has that level (rules and evidence) and the evidence itself.

const LEVELS = ['critical', 'high', 'medium', 'low'];
const LEVEL_LABEL = { critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low' };
const TYPE_LABEL = { referential: 'Referential', signature: 'Signature', semantic: 'Semantic' };

function SeverityBadge({ level, score }) {
  if (!level) return null;
  return (
    <span className={`severity-badge severity-${level}`} data-severity={level}>
      {LEVEL_LABEL[level] || level}
      {score !== undefined && score !== null && <span className="severity-score"> · {score}</span>}
    </span>
  );
}

function delta(value) {
  return value > 0 ? `+${value}` : String(value);
}

function SeverityReasons({ assessment }) {
  if (!assessment) return null;
  return (
    <div className="drift-why" aria-label="Why this severity">
      <h4>Why {LEVEL_LABEL[assessment.level]}</h4>
      <ul>
        <li>
          <strong>{assessment.base_label}</strong>: starts at {LEVEL_LABEL[assessment.base_level]}
          {assessment.base_evidence?.length > 0 && <span className="drift-evidence-ref"> [{assessment.base_evidence.join(', ')}]</span>}
          <p>{assessment.base_reason}</p>
        </li>
        {assessment.adjustments.map((step) => (
          <li key={step.rule}>
            <strong>{step.label}</strong>: {delta(step.delta)} level
            {step.evidence?.length > 0 && <span className="drift-evidence-ref"> [{step.evidence.join(', ')}]</span>}
            <p>{step.reason}</p>
          </li>
        ))}
        {assessment.capped_at && <li>Capped at {LEVEL_LABEL[assessment.capped_at]}.</li>}
      </ul>
    </div>
  );
}

function Evidence({ items }) {
  return (
    <ul className="drift-evidence">
      {items.map((item) => (
        <li key={item.id} id={`evidence-${item.id}`}>
          <span className="drift-evidence-id">{item.id}</span>
          {item.kind === 'code_diff' && (
            <>
              <span> code diff <code>{item.path}{item.line_start ? `:${item.line_start}` : ''}</code></span>
              <pre>{item.excerpt}</pre>
            </>
          )}
          {item.kind === 'documentation' && (
            <span> <code>{item.path}:{item.line_start}</code> — {item.excerpt}</span>
          )}
          {item.kind === 'commit' && (
            <span> commit {item.commit_sha ? <code>{item.commit_sha.slice(0, 7)}</code> : null} {item.excerpt}
              {item.url && <> · <a href={item.url} target="_blank" rel="noreferrer">open</a></>}
            </span>
          )}
          {item.kind === 'ticket' && <span> ticket {item.ticket}</span>}
        </li>
      ))}
    </ul>
  );
}

function Finding({ finding }) {
  const [open, setOpen] = useState(false);
  const part = finding.document || {};
  return (
    <article className={`drift-finding severity-border-${finding.severity}`} data-finding={finding.id}>
      <header className="drift-finding-heading">
        <SeverityBadge level={finding.severity} score={finding.severity_assessment?.score} />
        <span className="drift-kind">{TYPE_LABEL[finding.type] || finding.type} · {finding.kind}</span>
        {finding.breaking && <span className="drift-breaking">Breaking</span>}
        <span className="drift-finding-id">{finding.id}</span>
      </header>
      {finding.entity && <h3><code>{finding.entity}</code></h3>}
      <p>{finding.message}</p>
      <dl className="drift-facts">
        <dt>Where</dt>
        <dd><code>{part.path}</code>{part.document_id ? ` (saved document, v${part.version})` : ''}</dd>
        <dt>Suggestion</dt>
        <dd>{finding.suggestion}</dd>
        <dt>Confidence</dt>
        <dd>{Number(finding.confidence).toFixed(2)} ({finding.confidence_level})</dd>
      </dl>
      <button type="button" className="text-button" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        {open ? 'Hide severity reasons and evidence' : 'Why this severity? Show evidence'}
      </button>
      {open && (
        <div className="drift-details">
          <SeverityReasons assessment={finding.severity_assessment} />
          <h4>Evidence</h4>
          <Evidence items={finding.evidence || []} />
        </div>
      )}
    </article>
  );
}

export default function DocumentationDrift({ userId }) {
  const workspaceId = userId ? `ws-${userId}` : '';
  const [repositories, setRepositories] = useState([]);
  const [repositoryId, setRepositoryId] = useState('');
  const [pullRequest, setPullRequest] = useState('');
  const [includeRepositoryDocs, setIncludeRepositoryDocs] = useState(true);
  const [report, setReport] = useState(null);
  const [history, setHistory] = useState([]);
  const [levels, setLevels] = useState([]);
  const [minSeverity, setMinSeverity] = useState('all');
  const [loadingRepositories, setLoadingRepositories] = useState(Boolean(userId));
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState('');
  const [markdown, setMarkdown] = useState('');

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
    githubApi('/api/documentation/drift/severity-rules', { userId })
      .then((rules) => { if (!cancelled) setLevels(rules?.levels || []); })
      .catch(() => { /* the legend is optional */ });
    return () => { cancelled = true; };
  }, [userId, workspaceId]);

  useEffect(() => {
    if (!repositoryId) return undefined;
    let cancelled = false;
    githubApi(`/api/repositories/${encodeURIComponent(repositoryId)}/drift/reports`, { userId })
      .then((rows) => { if (!cancelled) setHistory(rows || []); })
      .catch(() => { if (!cancelled) setHistory([]); });
    return () => { cancelled = true; };
  }, [repositoryId, userId]);

  const shownFindings = useMemo(() => {
    const findings = report?.findings || [];
    if (minSeverity === 'all') return findings;
    const floor = LEVELS.indexOf(minSeverity);
    return findings.filter((finding) => LEVELS.indexOf(finding.severity) <= floor);
  }, [report, minSeverity]);

  async function refreshHistory() {
    try {
      setHistory(await githubApi(`/api/repositories/${encodeURIComponent(repositoryId)}/drift/reports`, { userId }) || []);
    } catch {
      setHistory([]);
    }
  }

  async function handleAnalyze(event) {
    event.preventDefault();
    setError('');
    setCopied('');
    const number = Number(pullRequest);
    if (!repositoryId) { setError('Add a repository to your workspace first.'); return; }
    if (!Number.isInteger(number) || number < 1) { setError('Enter a pull request number (1 or more).'); return; }
    setAnalyzing(true);
    try {
      const result = await githubApi(`/api/repositories/${encodeURIComponent(repositoryId)}/drift/analyze`, {
        method: 'POST', userId, body: { pullRequestNumber: number, includeRepositoryDocs },
      });
      setReport(result);
      setMinSeverity('all');
      setMarkdown('');
      await refreshHistory();
    } catch (requestError) {
      setError(requestError.message || 'The drift check failed. Please try again.');
    } finally {
      setAnalyzing(false);
    }
  }

  async function openReport(reportId) {
    setError('');
    setCopied('');
    try {
      setReport(await githubApi(`/api/repositories/${encodeURIComponent(repositoryId)}/drift/reports/${encodeURIComponent(reportId)}`, { userId }));
      setMinSeverity('all');
      setMarkdown('');
    } catch (requestError) {
      setError(requestError.message || 'Could not open the drift report.');
    }
  }

  async function copyMarkdown() {
    setCopied('');
    setMarkdown('');
    let text;
    try {
      const level = minSeverity === 'all' ? '' : `?minSeverity=${minSeverity}`;
      text = await githubApiText(`/api/repositories/${encodeURIComponent(repositoryId)}/drift/reports/${encodeURIComponent(report.id)}/markdown${level}`, { userId });
    } catch (requestError) {
      setCopied(requestError.message || 'Could not load the report.');
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setCopied('Markdown copied. Paste it as a pull request comment.');
    } catch {
      setMarkdown(text);      // clipboard not allowed: let the user copy it by hand
      setCopied('Copy the report below and paste it as a pull request comment.');
    }
  }

  const summary = report?.summary;
  return (
    <section className="login-card documentation-drift-page" aria-labelledby="documentation-drift-title">
      <h1 id="documentation-drift-title">Documentation Drift</h1>
      <p className="subtitle">Check a pull request for documentation that no longer matches the code, ranked by severity.</p>

      <form className="documentation-drift-form" onSubmit={handleAnalyze}>
        <label htmlFor="drift-repository">Repository</label>
        <select id="drift-repository" value={repositoryId} disabled={loadingRepositories || !repositories.length}
          onChange={(event) => { setRepositoryId(event.target.value); setReport(null); setError(''); }}>
          {repositories.length === 0 && <option value="">No workspace repositories</option>}
          {repositories.map((repository) => <option key={repository.id} value={repository.id}>{repository.fullName}</option>)}
        </select>
        <label htmlFor="drift-pull-request">Pull request number</label>
        <div className="documentation-drift-input-row">
          <input id="drift-pull-request" inputMode="numeric" value={pullRequest} placeholder="e.g. 42"
            onChange={(event) => setPullRequest(event.target.value.replace(/[^0-9]/g, ''))} />
          <button type="submit" disabled={analyzing || !repositoryId}>{analyzing ? 'Checking...' : 'Check drift'}</button>
        </div>
        <label className="drift-checkbox">
          <input type="checkbox" checked={includeRepositoryDocs} onChange={(event) => setIncludeRepositoryDocs(event.target.checked)} />
          Also check README and Markdown files of the repository
        </label>
      </form>
      {error && <p role="alert" className="drift-error">{error}</p>}

      {levels.length > 0 && (
        <details className="drift-legend">
          <summary>Severity levels</summary>
          <ul>
            {levels.map((item) => (
              <li key={item.level}>
                <SeverityBadge level={item.level} /> <span className="drift-band">{item.min_score}-{item.max_score}</span>
                {' '}{item.meaning} <em>{item.action}</em>
              </li>
            ))}
          </ul>
        </details>
      )}

      {report && (
        <div className="drift-report" aria-live="polite">
          <div className={`drift-overall severity-border-${summary?.highest_severity || 'none'}`}>
            {summary?.highest_severity ? (
              <>
                <div className="drift-overall-heading">
                  <span>Overall severity</span>
                  <SeverityBadge level={summary.highest_severity} score={summary.severity_score} />
                </div>
                <p className="drift-recommendation">{summary.recommendation}</p>
              </>
            ) : (
              <p className="drift-recommendation">No documentation drift: the checked documentation matches the code.</p>
            )}
            <p className="drift-meta">
              PR #{report.pull_request?.number}{report.pull_request?.title ? ` · ${report.pull_request.title}` : ''}
              {' · '}{summary?.findings || 0} finding(s) · {summary?.breaking || 0} breaking · {summary?.affected_documents || 0} document(s)
            </p>
          </div>

          {summary?.findings > 0 && (
            <div className="drift-filter" role="group" aria-label="Filter by severity">
              <button type="button" className={minSeverity === 'all' ? 'active' : ''} onClick={() => setMinSeverity('all')}>
                All ({summary.findings})
              </button>
              {LEVELS.map((level) => (
                <button key={level} type="button" data-level={level} className={minSeverity === level ? 'active' : ''}
                  onClick={() => setMinSeverity(level)} disabled={!summary.by_severity?.[level]}>
                  <SeverityBadge level={level} /> {summary.by_severity?.[level] || 0}
                </button>
              ))}
              <button type="button" className="drift-copy" onClick={copyMarkdown}>Copy as PR comment</button>
            </div>
          )}
          {minSeverity !== 'all' && <p className="drift-meta">Showing {LEVEL_LABEL[minSeverity]} and above: {shownFindings.length} of {summary.findings}.</p>}
          {copied && <p role="status" className="drift-meta">{copied}</p>}
          {markdown && <textarea className="drift-markdown" readOnly value={markdown} aria-label="Report as Markdown" rows={10} />}

          {report.affected_documents?.length > 0 && (
            <ul className="drift-documents" aria-label="Affected documentation">
              {report.affected_documents.map((part) => (
                <li key={`${part.source}-${part.document_id || ''}-${part.path}`}>
                  <SeverityBadge level={part.severity} /> <code>{part.path}</code>
                  <span className="drift-meta"> {part.findings} finding(s)</span>
                </li>
              ))}
            </ul>
          )}

          <div className="drift-findings">
            {shownFindings.map((finding) => <Finding key={finding.id} finding={finding} />)}
          </div>

          {report.warnings?.length > 0 && (
            <ul className="drift-warnings" aria-label="Warnings">
              {report.warnings.map((warning) => <li key={warning}>{warning}</li>)}
            </ul>
          )}
        </div>
      )}

      {history.length > 0 && (
        <div className="drift-history">
          <h2>Previous checks</h2>
          <ul>
            {history.map((row) => (
              <li key={row.id}>
                <button type="button" className="text-button" onClick={() => openReport(row.id)}>
                  PR #{row.pull_request_number}{row.pull_request_title ? ` · ${row.pull_request_title}` : ''}
                </button>
                <SeverityBadge level={row.summary?.highest_severity} />
                <span className="drift-meta"> {row.summary?.findings || 0} finding(s)</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}



