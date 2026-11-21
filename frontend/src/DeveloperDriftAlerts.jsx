import { useEffect, useState } from 'react';
import { githubApi } from './githubApi';
import PageFrame from './rbac/PageFrame';
import './DeveloperDriftAlerts.css';

function FindingReview({ finding, disabled, onReview }) {
  const [mode, setMode] = useState(null);
  const [text, setText] = useState('');
  const suggestion = finding.ai_review?.suggested_update || finding.suggestion;
  const resolution = finding.resolution;
  const draftVersion = resolution?.draft_version;
  const canDraft = Boolean(finding.document?.document_id && finding.document?.version);

  function begin(nextMode) {
    setMode(nextMode);
    setText(nextMode === 'edit' ? resolution?.proposed || suggestion : '');
  }

  async function submit(decision) {
    if (await onReview(finding.id, decision, text)) setMode(null);
  }

  return (
    <article className="drift-alert">
      <h3>{finding.message}</h3>
      <p>{finding.severity} · {finding.file}</p>
      {finding.document?.path && <p>Documentation: {finding.document.path}</p>}
      <details>
        <summary>Evidence</summary>
        <ul>{(finding.evidence || []).map((item, index) => (
          <li key={index}>{item.kind}: {item.excerpt || item.source || ''}</li>
        ))}</ul>
      </details>
      {suggestion && <pre>{suggestion}</pre>}
      {resolution?.decision && (
        <div role="status">
          {({ accept: 'Accepted', edit: 'Edited', dismiss: 'Dismissed' })[resolution.decision]}
          {draftVersion && <p>Draft v{draftVersion} · Submitted for Staff review</p>}
          {(resolution.proposed || resolution.note) && <pre>{resolution.proposed || resolution.note}</pre>}
        </div>
      )}
      {draftVersion ? null : mode ? (
        <form onSubmit={(event) => { event.preventDefault(); void submit(mode); }}>
          <label>
            {mode === 'edit' ? 'Proposed text' : 'Dismissal reason'}
            <textarea required maxLength={mode === 'edit' ? 20000 : 2000} value={text}
              onChange={(event) => setText(event.target.value)} />
          </label>
          <button disabled={disabled || !text.trim()} type="submit">
            {mode === 'edit' ? 'Save edit' : 'Confirm dismissal'}
          </button>
          <button disabled={disabled} type="button" onClick={() => setMode(null)}>Cancel</button>
        </form>
      ) : (
        <div className="drift-alert-actions">
          <button type="button" disabled={disabled || !suggestion || !canDraft} onClick={() => void submit('accept')}>Accept</button>
          <button type="button" disabled={disabled || !canDraft} onClick={() => begin('edit')}>Edit</button>
          <button type="button" disabled={disabled} onClick={() => begin('dismiss')}>Dismiss</button>
        </div>
      )}
    </article>
  );
}

export default function DeveloperDriftAlerts({ userId }) {
  const [repositories, setRepositories] = useState([]);
  const [repoId, setRepoId] = useState('');
  const [pullRequest, setPullRequest] = useState('');
  const [reports, setReports] = useState([]);
  const [sourceChanges, setSourceChanges] = useState(null);
  const [inboxError, setInboxError] = useState('');
  const [report, setReport] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loadingReports, setLoadingReports] = useState(false);
  const repositoryPath = repoId && `/api/repositories/${encodeURIComponent(repoId)}`;
  const base = repositoryPath && `${repositoryPath}/drift`;

  useEffect(() => {
    let current = true;
    githubApi(`/api/workspaces/${encodeURIComponent(`ws-${userId}`)}/repositories`)
      .then((rows) => {
        if (!current) return;
        setRepositories(rows);
        setRepoId(rows[0]?.id || '');
      })
      .catch((failure) => { if (current) setError(failure.message); });
    return () => { current = false; };
  }, [userId]);

  useEffect(() => {
    if (!base) return undefined;
    let current = true;
    githubApi(`${base}/reports`)
      .then((rows) => { if (current) setReports(rows); })
      .catch((failure) => { if (current) setError(failure.message); })
      .finally(() => { if (current) setLoadingReports(false); });
    return () => { current = false; };
  }, [base]);

  useEffect(() => {
    if (!repositoryPath) return undefined;
    let current = true;
    githubApi(`${repositoryPath}/source-changes`)
      .then((changes) => {
        if (current) setSourceChanges(changes.filter((change) =>
          change.documentsStatus === 'FOUND' && change.affectedDocuments?.length));
      })
      .catch((failure) => { if (current) setInboxError(failure.message); });
    return () => { current = false; };
  }, [repositoryPath]);

  async function run(request) {
    setBusy(true);
    setError('');
    try {
      await request();
      return true;
    } catch (failure) {
      setError(failure.message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  function chooseRepository(id) {
    setReports([]);
    setSourceChanges(null);
    setInboxError('');
    setReport(null);
    setError('');
    setLoadingReports(Boolean(id));
    setRepoId(id);
  }

  function analyze(event) {
    event.preventDefault();
    return analyzePullRequest(Number(pullRequest));
  }

  function analyzePullRequest(number) {
    setPullRequest(String(number));
    return run(async () => {
      const result = await githubApi(`${base}/analyze`, {
        method: 'POST', body: { pullRequestNumber: number },
      });
      setReport(result);
      setReports(await githubApi(`${base}/reports`));
    });
  }

  function review(findingId, decision, text) {
    return run(async () => {
      const updated = await githubApi(`${base}/reports/${encodeURIComponent(report.id)}/findings/${encodeURIComponent(findingId)}/resolution`, {
        method: 'PUT',
        body: {
          decision,
          status: decision === 'dismiss' ? 'dismissed' : 'acknowledged',
          ...(decision === 'edit' && { proposed: text }),
          ...(decision === 'dismiss' && { note: text }),
        },
      });
      setReport((previous) => ({
        ...previous, findings: previous.findings.map((finding) => finding.id === findingId ? updated : finding),
      }));
    });
  }

  return (
    <PageFrame title="Drift Alerts" titleId="drift-alerts-title" className="drift-alerts-page">
      <form onSubmit={analyze} className="drift-alert-form">
        <label>Repository
          <select value={repoId} disabled={busy} onChange={(event) => chooseRepository(event.target.value)}>
            {!repositories.length && <option value="">No connected repositories</option>}
            {repositories.map((repo) => <option key={repo.id} value={repo.id}>{repo.fullName}</option>)}
          </select>
        </label>
        <label>Pull request number
          <input type="number" required min="1" max="2147483647" value={pullRequest}
            onChange={(event) => setPullRequest(event.target.value)} />
        </label>
        <button disabled={!base || busy || loadingReports} type="submit">Check for drift</button>
      </form>
      {repositoryPath && (
        <section aria-label="Source changes affecting documentation">
          <h2>Source changes affecting documentation</h2>
          {inboxError && <p role="alert">{inboxError}</p>}
          {!inboxError && sourceChanges === null && <p role="status">Loading source changes…</p>}
          {sourceChanges?.length === 0 && <p>No affected documentation detected.</p>}
          <ul>
            {sourceChanges?.map((change) => (
              <li key={change.id}>
                {change.pullRequestNumber ? `Pull request #${change.pullRequestNumber}` : 'Commit'}
                {' · '}<code>{change.commitSha?.slice(0, 7)}</code>
                {' · '}{change.affectedDocuments.length} affected documentation section(s)
                {Number.isInteger(change.pullRequestNumber) && (
                  <button type="button" disabled={busy || loadingReports}
                    onClick={() => void analyzePullRequest(change.pullRequestNumber)}>
                    Review current PR #{change.pullRequestNumber}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      {base && (
        <label>Report history
          <select disabled={busy || loadingReports} value={report?.id || ''} onChange={(event) => {
            const id = event.target.value;
            if (!id) setReport(null);
            else void run(async () => {
              setReport(await githubApi(`${base}/reports/${encodeURIComponent(id)}`));
            });
          }}>
            <option value="">Select a report</option>
            {reports.map((row) => (
              <option key={row.id} value={row.id}>
                #{row.pull_request_number} · {row.pull_request_title} · {row.head_sha?.slice(0, 7)}
              </option>
            ))}
          </select>
        </label>
      )}
      {(busy || loadingReports) && <p role="status">Loading drift data…</p>}
      {error && <p role="alert">{error}</p>}
      {report && (
        <section aria-label="Findings">
          <h2>Pull request #{report.pull_request?.number}</h2>
          {report.warnings?.map((warning, index) => <p key={index}>{warning}</p>)}
          {!report.findings.length && <p>No drift found.</p>}
          {report.findings.map((finding) => (
            <FindingReview key={`${report.id}/${finding.id}`} finding={finding} disabled={busy} onReview={review} />
          ))}
        </section>
      )}
    </PageFrame>
  );
}
