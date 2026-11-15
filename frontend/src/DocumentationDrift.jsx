import { useEffect, useMemo, useState } from 'react';
import { githubApi, githubApiText } from './githubApi';

// LD-159 Display drift severity: run a drift check for a pull request and show every finding
// with its severity level, why it has that level (rules and evidence) and the evidence itself.

const LEVELS = ['critical', 'high', 'medium', 'low'];
const LEVEL_LABEL = { critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low' };
const TYPE_LABEL = { referential: 'Referential', signature: 'Signature', semantic: 'Semantic' };

function isDriftReport(value) {
  return Boolean(value && typeof value === 'object'
    && ['drift_detected', 'no_drift'].includes(value.status)
    && value.summary && typeof value.summary === 'object'
    && Number.isInteger(value.summary.findings)
    && Array.isArray(value.findings)
    && value.findings.every((finding) => finding && typeof finding === 'object')
    && value.pull_request && typeof value.pull_request === 'object');
}

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
        {(assessment.adjustments || []).map((step) => (
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
  if (!items?.length) return <p className="drift-meta">No evidence was returned for this finding.</p>;
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
  const location = part.path || finding.file || 'Location unavailable';
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
        <dd><code>{location}</code>{part.document_id ? ` (saved document, v${part.version})` : ''}</dd>
        <dt>Suggestion</dt>
        <dd>{finding.suggestion}</dd>
        <dt>Confidence</dt>
        <dd>{Number.isFinite(Number(finding.confidence))
          ? `${Number(finding.confidence).toFixed(2)} (${finding.confidence_level || 'level unavailable'})`
          : 'Not provided'}</dd>
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
  const [repositoryError, setRepositoryError] = useState('');
  const [repositoryLoadAttempt, setRepositoryLoadAttempt] = useState(0);
  const [severityRulesError, setSeverityRulesError] = useState('');
  const [severityRulesLoadAttempt, setSeverityRulesLoadAttempt] = useState(0);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState('');
  const [canRetryAnalysis, setCanRetryAnalysis] = useState(false);
  const [copied, setCopied] = useState('');
  const [markdown, setMarkdown] = useState('');
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [historyError, setHistoryError] = useState('');
  const [openingReportId, setOpeningReportId] = useState('');
  const [failedReportId, setFailedReportId] = useState('');

  useEffect(() => {
    if (!userId) return undefined;
    let cancelled = false;
    githubApi(`/api/workspaces/${encodeURIComponent(workspaceId)}/repositories`, { userId })
      .then((items) => {
        if (cancelled) return;
        if (!Array.isArray(items)) throw new Error('The repository list response was invalid.');
        setRepositories(items);
        setRepositoryId((current) => items?.some((item) => String(item.id) === current)
          ? current : String(items?.[0]?.id || ''));
      })
      .catch((requestError) => {
        if (!cancelled) setRepositoryError(requestError.message || 'Could not load repositories.');
      })
      .finally(() => { if (!cancelled) setLoadingRepositories(false); });
    return () => { cancelled = true; };
  }, [userId, workspaceId, repositoryLoadAttempt]);

  useEffect(() => {
    if (!userId) return undefined;
    let cancelled = false;
    githubApi('/api/documentation/drift/severity-rules', { userId })
      .then((rules) => {
        if (cancelled) return;
        if (!Array.isArray(rules?.levels)) throw new Error('The severity rules response was invalid.');
        setLevels(rules.levels);
      })
      .catch((requestError) => {
        if (!cancelled) setSeverityRulesError(requestError.message || 'Could not load severity guidance.');
      });
    return () => { cancelled = true; };
  }, [userId, severityRulesLoadAttempt]);

  useEffect(() => {
    if (!repositoryId) return undefined;
    let cancelled = false;
    githubApi(`/api/repositories/${encodeURIComponent(repositoryId)}/drift/reports`, { userId })
      .then((rows) => {
        if (cancelled) return;
        if (!Array.isArray(rows)) throw new Error('The drift history response was invalid.');
        setHistory(rows);
      })
      .catch((requestError) => {
        if (cancelled) return;
        setHistory([]);
        setHistoryError(requestError.message || 'Could not load previous drift checks.');
      })
      .finally(() => {
        if (!cancelled) {
          setHistoryLoaded(true);
          setLoadingHistory(false);
        }
      });
    return () => { cancelled = true; };
  }, [repositoryId, userId]);

  const shownFindings = useMemo(() => {
    const findings = report?.findings || [];
    if (minSeverity === 'all') return findings;
    const floor = LEVELS.indexOf(minSeverity);
    return findings.filter((finding) => {
      const index = LEVELS.indexOf(finding.severity);
      return index >= 0 && index <= floor;
    });
  }, [report, minSeverity]);

  async function refreshHistory() {
    if (!repositoryId) return;
    setLoadingHistory(true);
    setHistoryError('');
    try {
      const rows = await githubApi(`/api/repositories/${encodeURIComponent(repositoryId)}/drift/reports`, { userId });
      if (!Array.isArray(rows)) throw new Error('The drift history response was invalid.');
      setHistory(rows);
      setHistoryLoaded(true);
    } catch (requestError) {
      setHistory([]);
      setHistoryError(requestError.message || 'Could not load previous drift checks.');
    } finally {
      setLoadingHistory(false);
    }
  }

  async function handleAnalyze(event) {
    event?.preventDefault();
    if (analyzing) return;
    setError('');
    setCanRetryAnalysis(false);
    setCopied('');
    const number = Number(pullRequest);
    if (!repositoryId) { setError('Add a repository to your workspace first.'); return; }
    if (!Number.isInteger(number) || number < 1) { setError('Enter a pull request number (1 or more).'); return; }
    setAnalyzing(true);
    try {
      const result = await githubApi(`/api/repositories/${encodeURIComponent(repositoryId)}/drift/analyze`, {
        method: 'POST', userId, body: { pullRequestNumber: number, includeRepositoryDocs },
      });
      if (!isDriftReport(result)) throw new Error('The drift analysis response was invalid. Please try again.');
      setReport(result);
      setMinSeverity('all');
      setMarkdown('');
      await refreshHistory();
    } catch (requestError) {
      setError(requestError.message || 'The drift check failed. Please try again.');
      setCanRetryAnalysis(true);
    } finally {
      setAnalyzing(false);
    }
  }

  async function openReport(reportId) {
    setError('');
    setCanRetryAnalysis(false);
    setFailedReportId('');
    setCopied('');
    setOpeningReportId(reportId);
    try {
      const result = await githubApi(`/api/repositories/${encodeURIComponent(repositoryId)}/drift/reports/${encodeURIComponent(reportId)}`, { userId });
      if (!isDriftReport(result)) throw new Error('The drift report response was invalid.');
      setReport(result);
      setMinSeverity('all');
      setMarkdown('');
    } catch (requestError) {
      setError(requestError.message || 'Could not open the drift report.');
      setFailedReportId(reportId);
    } finally {
      setOpeningReportId('');
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
  const showHistoryLoading = loadingHistory || (Boolean(repositoryId) && !historyLoaded && !historyError);
  const reportStatus = report?.status === 'drift_detected'
    ? 'Drift detected'
    : report?.status === 'no_drift' ? 'No drift detected' : report?.status;
  return (
    <section className="login-card documentation-drift-page" aria-labelledby="documentation-drift-title">
      <h1 id="documentation-drift-title">Documentation Drift</h1>
      <p className="subtitle">Check a pull request for documentation that no longer matches the code, ranked by severity.</p>

      <form className="documentation-drift-form" onSubmit={handleAnalyze}>
        <label htmlFor="drift-repository">Repository</label>
        {loadingRepositories && <p role="status">Loading repositories…</p>}
        {repositoryError && <div className="drift-inline-error" role="alert">
          <span>{repositoryError}</span>
          <button type="button" className="text-button" onClick={() => {
            setLoadingRepositories(true);
            setRepositoryError('');
            setRepositoryLoadAttempt((n) => n + 1);
          }}>Retry loading repositories</button>
        </div>}
        <select id="drift-repository" value={repositoryId} disabled={loadingRepositories || !repositories.length}
          onChange={(event) => {
            setRepositoryId(event.target.value);
            setHistory([]);
            setHistoryLoaded(false);
            setHistoryError('');
            setLoadingHistory(Boolean(event.target.value));
            setReport(null);
            setError('');
          }}>
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
          <input type="checkbox" checked={includeRepositoryDocs} disabled={analyzing} onChange={(event) => setIncludeRepositoryDocs(event.target.checked)} />
          Also check README and Markdown files of the repository
        </label>
      </form>
      {error && <p role="alert" className="drift-error">{error}</p>}
      {error && failedReportId && (
        <button type="button" className="documentation-secondary-button drift-retry" disabled={Boolean(openingReportId)} onClick={() => openReport(failedReportId)}>
          Retry opening report
        </button>
      )}
      {analyzing && <p className="drift-loading" role="status" aria-live="polite">Analyzing Pull Request drift...</p>}
      {!loadingRepositories && !repositoryError && repositories.length === 0 && (
        <div className="drift-empty" role="status">
          <h2>No repositories available</h2>
          <p>Connect a repository in Repository Management before checking documentation drift.</p>
        </div>
      )}
      {error && canRetryAnalysis && repositoryId && Number.isInteger(Number(pullRequest)) && Number(pullRequest) > 0 && (
        <button type="button" className="documentation-secondary-button drift-retry" disabled={analyzing} onClick={handleAnalyze}>
          Retry drift analysis
        </button>
      )}

      {severityRulesError && <div className="drift-inline-error" role="alert">
        <span>{severityRulesError}</span>
        <button type="button" className="text-button" onClick={() => {
          setLevels([]);
          setSeverityRulesError('');
          setSeverityRulesLoadAttempt((n) => n + 1);
        }}>Retry severity guidance</button>
      </div>}
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
          <div className="drift-report-meta" aria-label="Analysis details">
            <span className={`drift-status drift-status-${report.status || 'unknown'}`} data-analysis-status={report.status || 'unknown'}>
              {reportStatus || 'Analysis status unavailable'}
            </span>
            <span><strong>Repository:</strong> {report.repository || repositories.find((item) => String(item.id) === repositoryId)?.fullName || 'Unavailable'}</span>
            {report.pull_request?.number != null && <span><strong>Pull Request:</strong> #{report.pull_request.number}{report.pull_request.title ? ` · ${report.pull_request.title}` : ''}</span>}
            {report.created_at && <span><strong>Analyzed:</strong> {new Date(report.created_at).toLocaleString()}</span>}
          </div>
          <div className={`drift-overall severity-border-${summary?.highest_severity || 'none'}`}>
            {summary?.highest_severity ? (
              <>
                <div className="drift-overall-heading">
                  <span>Overall severity</span>
                  <SeverityBadge level={summary.highest_severity} score={summary.severity_score} />
                </div>
                <p className="drift-recommendation">{summary.recommendation}</p>
              </>
            ) : report.status === 'no_drift' && report.findings.length === 0 ? (
              <p className="drift-recommendation">No documentation drift: the checked documentation matches the code.</p>
            ) : report.status === 'drift_detected' ? (
              <p className="drift-recommendation">Drift was detected, but severity details are unavailable in this report.</p>
            ) : (
              <p className="drift-recommendation">The analysis did not return enough information to determine drift status.</p>
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

      {report && summary?.findings > 0 && shownFindings.length === 0 && (
        <p className="drift-empty" role="status">No findings match the selected severity filter.</p>
      )}

      <section className="drift-history" aria-labelledby="drift-history-heading">
        <h2 id="drift-history-heading">Previous checks</h2>
        {openingReportId && <p role="status">Opening selected report...</p>}
        {showHistoryLoading && <p role="status">Loading previous checks...</p>}
        {!showHistoryLoading && historyError && <div className="drift-inline-error" role="alert">
          <span>{historyError}</span>
          <button type="button" className="text-button" onClick={() => void refreshHistory()}>Retry loading history</button>
        </div>}
        {!showHistoryLoading && !historyError && historyLoaded && history.length === 0 && (
          <p className="drift-empty" role="status">No previous drift checks for this repository.</p>
        )}
        {!showHistoryLoading && !historyError && history.length > 0 && (
          <ul>
            {history.map((row) => (
              <li key={row.id}>
                <button type="button" className="text-button" disabled={analyzing || Boolean(openingReportId)} onClick={() => openReport(row.id)}>
                  PR #{row.pull_request_number}{row.pull_request_title ? ` - ${row.pull_request_title}` : ''}
                </button>
                <span className={`drift-status drift-status-${row.status || 'unknown'}`}>{row.status || 'Status unavailable'}</span>
                <SeverityBadge level={row.summary?.highest_severity} />
                <span className="drift-meta">{row.summary?.findings || 0} finding(s)</span>
                {row.created_at && <time className="drift-meta" dateTime={row.created_at}>{new Date(row.created_at).toLocaleString()}</time>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}
