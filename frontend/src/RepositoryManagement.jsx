import { useCallback, useEffect, useMemo, useState } from 'react';
import './App.css';
import { githubApi } from './githubApi';

export default function RepositoryManagement({ userId }) {
  const workspaceId = userId ? `ws-${userId}` : '';
  const [search, setSearch] = useState('');
  const [visibility, setVisibility] = useState('all');
  const [selectedIds, setSelectedIds] = useState([]);
  const [availableRepositories, setAvailableRepositories] = useState([]);
  const [workspaceRepositories, setWorkspaceRepositories] = useState([]);
  const [activeTab, setActiveTab] = useState('available');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [syncErrors, setSyncErrors] = useState({});
  const [syncingIds, setSyncingIds] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(Boolean(userId));
  const [isAdding, setIsAdding] = useState(false);

  const refreshRepositories = useCallback(async (active = true) => {
    if (!userId) {
      setAvailableRepositories([]);
      setWorkspaceRepositories([]);
      setIsConnected(false);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError('');
    try {
      const connection = await githubApi('/api/github/connection', { userId });
      setIsConnected(Boolean(connection.connected));
      const workspace = await githubApi(`/api/workspaces/${workspaceId}/repositories`, { userId });
      setWorkspaceRepositories(workspace || []);
      const available = connection.connected
        ? await githubApi('/api/github/repos/available', { userId })
        : [];
      setAvailableRepositories(available || []);
    } catch (requestError) {
      if (active) setError(requestError.message || 'Could not load repositories.');
    } finally {
      if (active) setIsLoading(false);
    }
  }, [userId, workspaceId]);

  useEffect(() => {
    let active = true;
    Promise.resolve().then(() => {
      if (active) refreshRepositories(active);
    });
    return () => { active = false; };
  }, [refreshRepositories]);

  const workspaceGithubIds = useMemo(
    () => new Set(workspaceRepositories.map((repo) => repo.githubRepoId)),
    [workspaceRepositories],
  );

  const filteredRepositories = useMemo(() => {
    const source = activeTab === 'available'
      ? availableRepositories.filter((repo) => !workspaceGithubIds.has(repo.githubRepoId))
      : workspaceRepositories;
    return source.filter((repo) => {
      const matchesSearch = repo.fullName.toLowerCase().includes(search.trim().toLowerCase());
      const matchesVisibility = visibility === 'all'
        || (visibility === 'public' && !repo.privateRepo)
        || (visibility === 'private' && repo.privateRepo);
      return matchesSearch && matchesVisibility;
    });
  }, [activeTab, availableRepositories, search, visibility, workspaceGithubIds, workspaceRepositories]);

  function toggleSelection(repoId) {
    setSelectedIds((current) => current.includes(repoId)
      ? current.filter((id) => id !== repoId)
      : [...current, repoId]);
    setMessage('');
  }

  async function addSelectedRepositories() {
    if (!selectedIds.length) {
      setMessage('Select at least one repository.');
      return;
    }
    setIsAdding(true);
    setError('');
    setMessage('');
    try {
      await githubApi(`/api/workspaces/${workspaceId}/repositories`, {
        method: 'POST',
        userId,
        body: { githubRepoIds: selectedIds },
      });
      setSelectedIds([]);
      setMessage('Selected repositories added to workspace.');
      await refreshRepositories();
    } catch (requestError) {
      setError(requestError.message || 'Could not add repositories to the workspace.');
    } finally {
      setIsAdding(false);
    }
  }

  async function connectGitHub() {
    setError('');
    try {
      const urls = await githubApi('/api/github/authorize-url', { userId });
      window.location.assign(urls.authorizeUrl);
    } catch (requestError) {
      setError(requestError.message || 'Could not start GitHub authorization.');
    }
  }

  async function syncRepository(repository) {
    setSyncingIds((current) => [...current, repository.id]);
    setSyncErrors((current) => ({ ...current, [repository.id]: '' }));
    setError('');
    try {
      const result = await githubApi(`/api/repositories/${repository.id}/sync`, {
        method: 'POST',
        userId,
      });
      setWorkspaceRepositories((current) => current.map((repo) => repo.id === repository.id
        ? { ...repo, status: 'CONNECTED', lastSyncedAt: result.syncedAt || new Date().toISOString() }
        : repo));
      setMessage(`${repository.fullName} synchronized.`);
    } catch (requestError) {
      const detail = requestError.retryAfter
        ? `${requestError.message} Retry after ${requestError.retryAfter} seconds.`
        : requestError.message || 'Repository synchronization failed.';
      setSyncErrors((current) => ({ ...current, [repository.id]: detail }));
    } finally {
      setSyncingIds((current) => current.filter((id) => id !== repository.id));
    }
  }

  async function removeFromWorkspace(repository) {
    setError('');
    try {
      await githubApi(`/api/repositories/${repository.id}`, { method: 'DELETE', userId });
      setWorkspaceRepositories((current) => current.filter((repo) => repo.id !== repository.id));
      setMessage(`${repository.fullName} removed from workspace.`);
    } catch (requestError) {
      setError(requestError.message || 'Could not remove repository.');
    }
  }

  const syncedCount = workspaceRepositories.filter((repo) => repo.lastSyncedAt).length;

  return (
    <main className="page">
      <section className="login-card repository-page">
        <h1>Repository Management</h1>
        <p className="subtitle">Manage GitHub repositories and synchronize your workspace.</p>

        {!userId ? (
          <p role="alert">Sign in to LivingDocs to load your GitHub repositories.</p>
        ) : (
          <>
            <section className="sync-connection-panel">
              <div>
                <strong>GitHub connection</strong>
                <p>{isConnected ? 'Connected to GitHub.' : 'GitHub is not connected.'}</p>
              </div>
              <span className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`} role="status">
                <span className="status-dot" aria-hidden="true" />
                {isConnected ? 'Connected' : 'Disconnected'}
              </span>
              {!isConnected && (
                <button type="button" onClick={connectGitHub}>Connect GitHub</button>
              )}
              <button type="button" className="sync-secondary-button" onClick={() => refreshRepositories()}>
                Refresh
              </button>
            </section>

            <div className="repository-stats">
              <div className="repository-stat"><span>Available repositories</span><strong>{availableRepositories.length}</strong></div>
              <div className="repository-stat"><span>Workspace repositories</span><strong>{workspaceRepositories.length}</strong></div>
              <div className="repository-stat"><span>Synced repositories</span><strong>{syncedCount}</strong></div>
            </div>

            <div className="repository-tabs">
              <button type="button" className={activeTab === 'available' ? 'active' : ''} onClick={() => setActiveTab('available')}>
                Available repositories
              </button>
              <button type="button" className={activeTab === 'workspace' ? 'active' : ''} onClick={() => setActiveTab('workspace')}>
                Workspace ({workspaceRepositories.length})
              </button>
            </div>

            <div className="repository-toolbar">
              <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search repositories..." aria-label="Search repositories" />
              <select value={visibility} onChange={(event) => setVisibility(event.target.value)} aria-label="Filter repositories by visibility">
                <option value="all">All repositories</option>
                <option value="public">Public</option>
                <option value="private">Private</option>
              </select>
            </div>

            {activeTab === 'available' && (
              <div className="repository-actions">
                <span>{selectedIds.length} selected</span>
                <button type="button" disabled={isAdding || !isConnected} onClick={addSelectedRepositories}>
                  {isAdding ? 'Adding…' : 'Add selected to workspace'}
                </button>
              </div>
            )}

            {isLoading && <p role="status">Loading repositories…</p>}
            {error && <p className="sync-error" role="alert">{error}</p>}
            {message && <p className="repository-message" role="status">{message}</p>}
            <p className="repository-result-count" role="status">Showing {filteredRepositories.length} repositories</p>

            {!isLoading && filteredRepositories.length === 0 ? (
              <div className="repository-empty">
                <h2>No repositories found</h2>
                <p>{!isConnected ? 'Connect GitHub to view repositories.' : 'Try another search or filter.'}</p>
              </div>
            ) : (
              <ul className="repository-list">
                {filteredRepositories.map((repo) => {
                  const inWorkspace = activeTab === 'workspace';
                  const syncing = syncingIds.includes(repo.id);
                  const syncError = syncErrors[repo.id];
                  return (
                    <li className="repository-item repository-sync-item" key={repo.id || repo.githubRepoId}>
                      {!inWorkspace && (
                        <input type="checkbox" aria-label={`Select ${repo.fullName}`} checked={selectedIds.includes(repo.githubRepoId)} onChange={() => toggleSelection(repo.githubRepoId)} />
                      )}
                      <div className="repository-info">
                        <h2>{repo.fullName}</h2>
                        <div className="repository-meta">
                          <span>{repo.privateRepo ? 'Private' : 'Public'}</span>
                          <span>Branch: {repo.defaultBranch}</span>
                          {inWorkspace && <span>Added to workspace</span>}
                        </div>
                        <div className="sync-details">
                          <span className={`sync-status sync-${syncing ? 'syncing' : syncError ? 'failed' : repo.status === 'ERROR' ? 'failed' : repo.lastSyncedAt ? 'synced' : 'not-synced'}`}>
                            {syncing ? 'Syncing…' : syncError || repo.status === 'ERROR' ? 'Sync failed' : repo.lastSyncedAt ? 'Synced' : 'Not synced'}
                          </span>
                          {repo.lastSyncedAt && <p className="sync-last-time">Last synced: {new Date(repo.lastSyncedAt).toLocaleString()}</p>}
                          {syncError && <p className="sync-error" role="alert">{syncError}</p>}
                        </div>
                        <div className="sync-actions">
                          {inWorkspace && (
                            <button type="button" disabled={syncing || !isConnected} onClick={() => syncRepository(repo)}>
                              {syncing ? 'Syncing…' : syncError ? 'Retry sync' : 'Sync now'}
                            </button>
                          )}
                          {inWorkspace && (
                            <button type="button" className="sync-secondary-button" onClick={() => removeFromWorkspace(repo)}>
                              Remove
                            </button>
                          )}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
            <p className="repository-disclaimer">Repositories, workspace membership, and synchronization are loaded from GitHub Integration Service.</p>
          </>
        )}
      </section>
    </main>
  );
}
