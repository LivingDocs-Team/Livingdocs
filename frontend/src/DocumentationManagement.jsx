
import { useEffect, useState } from 'react';
import './App.css';
import { githubApi, githubApiText } from './githubApi';
import { TemplateManager, TemplatePicker } from './DocumentationTemplates';
import { useTemplates } from './templateApi';


function escapeHtml(value) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Small Markdown renderer for this frontend demo.
// It intentionally supports common Markdown syntax only.
function renderMarkdown(markdown) {
  const lines = markdown.split('\n');
  const output = [];
  let inList = false;
  let inCode = false;
  let codeLines = [];

  function closeList() {
    if (inList) {
      output.push('</ul>');
      inList = false;
    }
  }

  for (const line of lines) {
    if (line.trim().startsWith('```')) {
      closeList();

      if (inCode) {
        output.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`);
        codeLines = [];
        inCode = false;
      } else {
        inCode = true;
      }
      continue;
    }

    if (inCode) {
      codeLines.push(line);
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      if (!inList) {
        output.push('<ul>');
        inList = true;
      }

      output.push(
        `<li>${escapeHtml(line.replace(/^\s*[-*]\s+/, ''))}</li>`
      );
      continue;
    }

    closeList();

    if (/^###\s+/.test(line)) {
      output.push(`<h3>${escapeHtml(line.replace(/^###\s+/, ''))}</h3>`);
    } else if (/^##\s+/.test(line)) {
      output.push(`<h2>${escapeHtml(line.replace(/^##\s+/, ''))}</h2>`);
    } else if (/^#\s+/.test(line)) {
      output.push(`<h1>${escapeHtml(line.replace(/^#\s+/, ''))}</h1>`);
    } else if (/^\d+\.\s+/.test(line)) {
      output.push(`<p>${escapeHtml(line)}</p>`);
    } else if (line.trim() === '---') {
      output.push('<hr />');
    } else if (line.trim() === '') {
      output.push('<div class="markdown-spacer"></div>');
    } else {
      output.push(`<p>${escapeHtml(line)}</p>`);
    }
  }

  closeList();

  if (inCode) {
    output.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`);
  }

  return output.join('\n');
}

export default function DocumentationManagement({ userId }) {
  const workspaceId = userId ? `ws-${userId}` : '';
  const [repositories, setRepositories] = useState([]);
  const [repositoryId, setRepositoryId] = useState('');
  const [template, setTemplate] = useState('default');
  const [isManagingTemplates, setIsManagingTemplates] = useState(false);
  const templateList = useTemplates(userId);
  const [status, setStatus] = useState('idle');
  const [document, setDocument] = useState('');
  const [evidence, setEvidence] = useState([]);
  const [error, setError] = useState('');

  const [activeTab, setActiveTab] = useState('edit');
  const [savedDocument, setSavedDocument] = useState('');
  const [versions, setVersions] = useState([]);
  const [selectedVersionId, setSelectedVersionId] = useState('');
  const [compareVersionId, setCompareVersionId] = useState('');
  const [notice, setNotice] = useState('');
  const [isLoadingRepositories, setIsLoadingRepositories] = useState(Boolean(userId));
  const [jobId, setJobId] = useState('');

  useEffect(() => {
    if (!userId) return undefined;

    let cancelled = false;
    Promise.resolve().then(() => {
      if (!cancelled) setIsLoadingRepositories(true);
      return githubApi(`/api/workspaces/${workspaceId}/repositories`, { userId });
    })
      .then((items) => {
        if (cancelled) return;
        setRepositories(items || []);
        setRepositoryId((current) => (
          items?.some((item) => String(item.id) === String(current))
            ? current
            : String(items?.[0]?.id || '')
        ));
        setError(items?.length ? '' : 'Add a repository to your workspace before generating documentation.');
      })
      .catch((requestError) => {
        if (!cancelled) setError(requestError.message || 'Could not load workspace repositories.');
      })
      .finally(() => {
        if (!cancelled) setIsLoadingRepositories(false);
      });

    return () => { cancelled = true; };
  }, [userId, workspaceId]);

  async function handleGenerate(event) {
    event.preventDefault();
    if (!userId || !repositoryId) {
      setError('Select a workspace repository before generating documentation.');
      return;
    }

    setStatus('generating');
    setError('');
    setNotice('');
    setDocument('');
    setSavedDocument('');
    setEvidence([]);
    setVersions([]);
    setSelectedVersionId('');
    setCompareVersionId('');
    setActiveTab('edit');
    setJobId('');

    try {
      const createdJob = await githubApi(`/api/repositories/${repositoryId}/documentation/generate`, {
        method: 'POST',
        userId,
        body: { templateId: template, outputLanguage: 'vi' },
      });
      if (!createdJob?.id) throw new Error('The documentation service returned an invalid job.');
      setJobId(createdJob.id);

      const deadline = Date.now() + 120_000;
      let job = createdJob;
      while (['pending', 'running'].includes(job.status) && Date.now() < deadline) {
        await new Promise((resolve) => window.setTimeout(resolve, 750));
        job = await githubApi(`/api/documentation/jobs/${encodeURIComponent(createdJob.id)}`, { userId });
      }
      if (['pending', 'running'].includes(job.status)) {
        throw new Error('Documentation generation timed out. You can retry from this page.');
      }
      if (job.status !== 'completed') {
        throw new Error(job.error || job.message || 'Documentation generation failed.');
      }

      const jobPath = `/api/documentation/jobs/${encodeURIComponent(createdJob.id)}`;
      const [markdown, report] = await Promise.all([
        githubApiText(`${jobPath}/result`, { userId }),
        githubApi(`${jobPath}/report`, { userId }),
      ]);
      if (!markdown.trim()) throw new Error('The documentation service returned an empty document.');
      const evidenceItems = (report.files || []).flatMap((file) => (file.entities || []).flatMap((entity) =>
        (entity.evidence || []).map((item) => {
          const location = item.line_start
            ? `${item.path}:${item.line_start}${item.line_end ? `-${item.line_end}` : ''}`
            : item.path;
          return `${entity.name} — ${location}`;
        }),
      ));

      setDocument(markdown);
      setSavedDocument(markdown);
      setEvidence(evidenceItems);
      setStatus('completed');
      const repoName = repositories.find((repo) => String(repo.id) === String(repositoryId))?.fullName;
      const templateName = job.template_name
        || templateList.templates.find((item) => item.id === template)?.name;
      setNotice(`Documentation generated from ${repoName || 'the selected repository'}`
        + (templateName ? ` using the "${templateName}" template.` : '.'));
    } catch (requestError) {
      setStatus('failed');
      if (requestError.code === 'TEMPLATE_NOT_FOUND') {
        templateList.reload();
        setTemplate('default');
      }
      setError(requestError.message || 'Documentation generation failed.');
    }
  }

  function handleReset() {
    setStatus('idle');
    setDocument('');
    setSavedDocument('');
    setEvidence([]);
    setError('');
    setNotice('');
    setVersions([]);
    setSelectedVersionId('');
    setCompareVersionId('');
    setActiveTab('edit');
    setJobId('');
  }

  function handleSaveDraft() {
    if (!document.trim()) {
      setError('Document content cannot be empty.');
      return;
    }

    setSavedDocument(document);
    setError('');
    setNotice('Draft saved in this page session.');
  }

  function handleCreateVersion() {
    if (!document.trim()) {
      setError('Generate or enter document content before creating a version.');
      return;
    }

    const version = {
      id: `${Date.now()}-${versions.length + 1}`,
      number: versions.length + 1,
      content: document,
      createdAt: new Date().toLocaleString(),
      label: `Version ${versions.length + 1}`,
    };

    setVersions((current) => [...current, version]);
    setSelectedVersionId(version.id);
    setError('');
    setNotice(`${version.label} created.`);
  }

  function handleRollback() {
    const version = versions.find((item) => item.id === selectedVersionId);

    if (!version) {
      setError('Select a version to restore.');
      return;
    }

    const confirmed = window.confirm(
      `Restore ${version.label}? Current unsaved edits will be replaced.`
    );

    if (!confirmed) return;

    setDocument(version.content);
    setSavedDocument(version.content);
    setError('');
    setNotice(`Content restored from ${version.label}.`);
    setActiveTab('edit');
  }

  function handleExport() {
    const blob = new Blob([document], {
      type: 'text/markdown;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const link = window.document.createElement('a');

    link.href = url;
    link.download = 'livingdocs-documentation.md';
    link.click();

    URL.revokeObjectURL(url);
  }

  const selectedVersion = versions.find(
    (version) => version.id === selectedVersionId
  );

  const compareVersion = versions.find(
    (version) => version.id === compareVersionId
  );

  const currentLines = document.split('\n');
  const comparisonLines = compareVersion
    ? compareVersion.content.split('\n')
    : [];

  return (
    <main className="page">
      <section className="login-card documentation-page">
        <h1>Documentation Management</h1>
        <p className="subtitle">
          Generate, preview, edit, and manage documentation versions.
        </p>

        <div className="documentation-status" role="status" aria-live="polite">
          <span className={`documentation-status-badge status-${status}`}>
            {status === 'idle' && 'Ready to generate'}
            {status === 'generating' && 'Generating…'}
            {status === 'completed' && 'Generation completed'}
            {status === 'failed' && 'Generation failed'}
          </span>
        </div>

        <form className="documentation-form" onSubmit={handleGenerate}>
          <label htmlFor="documentation-repository">Repository</label>
          <select
            id="documentation-repository"
            value={repositoryId}
            onChange={(event) => setRepositoryId(event.target.value)}
            required
          >
            {repositories.map((item) => (
              <option key={item.id} value={item.id}>{item.fullName}</option>
            ))}
          </select>

          <div className="documentation-template-heading">
            <label id="documentation-template-label">Documentation template</label>
            <button
              type="button"
              className="documentation-secondary-button"
              aria-expanded={isManagingTemplates}
              onClick={() => setIsManagingTemplates((open) => !open)}
            >
              {isManagingTemplates ? 'Close template manager' : 'Manage templates'}
            </button>
          </div>
          <TemplatePicker
            templates={templateList.templates}
            value={template}
            onChange={setTemplate}
            isLoading={templateList.isLoading}
            loadError={templateList.loadError}
            disabled={status === 'generating'}
          />

          <div className="documentation-actions">
            <button type="submit" disabled={status === 'generating' || isLoadingRepositories || repositories.length === 0
              || !templateList.templates.some((item) => item.id === template)}>
              {status === 'generating' ? 'Generating…' : 'Generate documentation'}
            </button>
            <button
              type="button"
              className="documentation-secondary-button"
              onClick={handleReset}
            >
              Reset
            </button>
          </div>
        </form>

        {isManagingTemplates && (
          <TemplateManager
            templates={templateList.templates}
            onSaved={(saved) => {
              templateList.reload();
              setTemplate(saved.id);
            }}
            onDeleted={(deleted) => {
              templateList.reload();
              if (deleted.id === template) setTemplate('default');
            }}
          />
        )}

        {isLoadingRepositories && <p role="status">Loading workspace repositories…</p>}

        {(!userId || error) && (
          <p className="documentation-error" role="alert">
            {!userId ? 'Sign in to LivingDocs before generating documentation.' : error}
          </p>
        )}

        {notice && (
          <p className="documentation-notice" role="status">{notice}</p>
        )}

        {status === 'generating' && (
          <p className="documentation-hint">
            Sending synchronized source files through code analysis and documentation generation…
          </p>
        )}

        {status === 'completed' && (
          <div className="documentation-result">
            <h2>Generated Documentation</h2>

            <div className="documentation-tabs" role="tablist" aria-label="Documentation views">
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'edit'}
                className={activeTab === 'edit' ? 'active' : ''}
                onClick={() => setActiveTab('edit')}
              >
                Edit
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'preview'}
                className={activeTab === 'preview' ? 'active' : ''}
                onClick={() => setActiveTab('preview')}
              >
                Preview
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'versions'}
                className={activeTab === 'versions' ? 'active' : ''}
                onClick={() => setActiveTab('versions')}
              >
                Versions ({versions.length})
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'diff'}
                className={activeTab === 'diff' ? 'active' : ''}
                onClick={() => setActiveTab('diff')}
              >
                Compare
              </button>
            </div>

            {activeTab === 'edit' && (
              <section className="documentation-panel">
                <label htmlFor="documentation-editor">
                  Markdown content
                </label>
                <textarea
                  id="documentation-editor"
                  className="documentation-editor"
                  value={document}
                  onChange={(event) => {
                    setDocument(event.target.value);
                    setNotice('');
                  }}
                  rows={18}
                />

                <div className="documentation-actions">
                  <button type="button" onClick={handleSaveDraft}>
                    Save draft
                  </button>
                  <button
                    type="button"
                    className="documentation-secondary-button"
                    onClick={handleCreateVersion}
                  >
                    Create version
                  </button>
                  <button
                    type="button"
                    className="documentation-secondary-button"
                    onClick={handleExport}
                  >
                    Export Markdown
                  </button>
                </div>

                <p className="documentation-hint">
                  {document === savedDocument
                    ? 'All changes saved in the current page session.'
                    : 'You have unsaved edits.'}
                </p>
              </section>
            )}

            {activeTab === 'preview' && (
              <section className="documentation-preview">
                <div className="documentation-preview-heading">
                  <h3>Document Preview</h3>
                  <span>Markdown preview</span>
                </div>
                {document.trim() ? (
                  <article
                    className="markdown-preview-content"
                    dangerouslySetInnerHTML={{
                      __html: renderMarkdown(document),
                    }}
                  />
                ) : (
                  <p>No content to preview.</p>
                )}
              </section>
            )}

            {activeTab === 'versions' && (
              <section className="documentation-panel">
                <div className="documentation-version-heading">
                  <h3>Version History</h3>
                  <button type="button" onClick={handleCreateVersion}>
                    Create version
                  </button>
                </div>

                {versions.length === 0 ? (
                  <div className="documentation-empty">
                    <h3>No versions yet</h3>
                    <p>Create a version to preserve the current document.</p>
                  </div>
                ) : (
                  <>
                    <label htmlFor="selected-version">Select version</label>
                    <select
                      id="selected-version"
                      value={selectedVersionId}
                      onChange={(event) => setSelectedVersionId(event.target.value)}
                    >
                      {versions.map((version) => (
                        <option key={version.id} value={version.id}>
                          {version.label} — {version.createdAt}
                        </option>
                      ))}
                    </select>

                    {selectedVersion && (
                      <div className="documentation-version-card">
                        <strong>{selectedVersion.label}</strong>
                        <p>Created: {selectedVersion.createdAt}</p>
                        <p>{selectedVersion.content.length} characters</p>
                        <button
                          type="button"
                          className="documentation-secondary-button"
                          onClick={handleRollback}
                        >
                          Restore this version
                        </button>
                      </div>
                    )}
                  </>
                )}
                <p className="documentation-hint">
                  Versions are stored in React state and disappear when this page is reloaded.
                </p>
              </section>
            )}

            {activeTab === 'diff' && (
              <section className="documentation-panel">
                <h3>Compare Documentation</h3>
                <p className="documentation-hint">
                  Choose a saved version to compare it with the current editor content.
                </p>

                <label htmlFor="compare-version">Compare with version</label>
                <select
                  id="compare-version"
                  value={compareVersionId}
                  onChange={(event) => setCompareVersionId(event.target.value)}
                >
                  <option value="">Choose a version</option>
                  {versions.map((version) => (
                    <option key={version.id} value={version.id}>
                      {version.label} — {version.createdAt}
                    </option>
                  ))}
                </select>

                {compareVersion ? (
                  <div className="documentation-diff">
                    <div className="documentation-diff-column">
                      <h4>Saved version</h4>
                      {comparisonLines.map((line, index) => {
                        const changed = currentLines[index] !== line;
                        return (
                          <div
                            key={`${index}-${line}`}
                            className={`documentation-diff-line ${changed ? 'diff-removed' : ''}`}
                          >
                            <span>{changed ? '−' : ' '}</span>
                            {line || ' '}
                          </div>
                        );
                      })}
                    </div>

                    <div className="documentation-diff-column">
                      <h4>Current document</h4>
                      {currentLines.map((line, index) => {
                        const changed = comparisonLines[index] !== line;
                        return (
                          <div
                            key={`${index}-${line}`}
                            className={`documentation-diff-line ${changed ? 'diff-added' : ''}`}
                          >
                            <span>{changed ? '+' : ' '}</span>
                            {line || ' '}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <div className="documentation-empty">
                    <p>
                      {versions.length
                        ? 'Select a version to display the comparison.'
                        : 'Create a version first to enable comparison.'}
                    </p>
                  </div>
                )}
              </section>
            )}

            <section className="documentation-evidence">
              <h2>Grounding Evidence</h2>
              <p>
                Evidence below is returned by the AI service report for this generation job.
              </p>
              <ul>
                {evidence.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </section>
          </div>
        )}

        {jobId && <p className="documentation-hint">Generation job: {jobId}</p>}
        <p className="documentation-disclaimer">
          Generated output comes from the latest synchronized repository snapshot. Draft edits and version history remain in this page session.
        </p>
      </section>
    </main>
  );
}
