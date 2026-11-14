import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import './App.css';
import { githubApi } from './githubApi';
import RepositoryActivity from './RepositoryActivity';

export default function RepositoryManagement({ userId }) {
  return <RepositoryManagementForUser key={userId ?? 'anonymous'} userId={userId} />;
}

function RepositoryManagementForUser({ userId }) {
  const personalWorkspaceId = userId ? `ws-${userId}` : '';
  const [workspaceId, setWorkspaceId] = useState(personalWorkspaceId);
  const refreshSequence = useRef(0);
  const selectedWorkspaceContext = useRef({ userId, workspaceId: personalWorkspaceId });
  const isMounted = useRef(false);
  const [search, setSearch] = useState('');
  const [visibility, setVisibility] = useState('all');
  const [selectedIds, setSelectedIds] = useState([]);
  const [availableRepositories, setAvailableRepositories] = useState([]);
  const [workspaceRepositories, setWorkspaceRepositories] = useState([]);
  const [managedWorkspaces, setManagedWorkspaces] = useState([]);
  const [isWorkspaceOwner, setIsWorkspaceOwner] = useState(false);
  const [reassignmentTargets, setReassignmentTargets] = useState({});
  const [reassigningIds, setReassigningIds] = useState([]);
  const [activeTab, setActiveTab] = useState('available');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [syncErrors, setSyncErrors] = useState({});
  const [syncingIds, setSyncingIds] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('DISCONNECTED');
  const [isLoading, setIsLoading] = useState(Boolean(userId));
  const [isAdding, setIsAdding] = useState(false);
  const [activityRepoId, setActivityRepoId] = useState(null);

  const isCurrentWorkspace = useCallback((expectedUserId, expectedWorkspaceId) => (
    isMounted.current
      && selectedWorkspaceContext.current.userId === expectedUserId
      && selectedWorkspaceContext.current.workspaceId === expectedWorkspaceId
  ), []);

  const refreshRepositories = useCallback(async (
    expectedUserId = userId,
    expectedWorkspaceId = workspaceId,
  ) => {
    // Check workspace identity before incrementing the sequence so an old callback
    // cannot invalidate a refresh for the newly selected workspace.
    if (!isCurrentWorkspace(expectedUserId, expectedWorkspaceId)) return;
    const requestId = ++refreshSequence.current;
    const isCurrentRequest = () => requestId === refreshSequence.current
      && isCurrentWorkspace(expectedUserId, expectedWorkspaceId);

    if (!expectedUserId) {
      setAvailableRepositories([]);
      setWorkspaceRepositories([]);
      setManagedWorkspaces([]);
      setIsConnected(false);
      setConnectionStatus('DISCONNECTED');
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError('');
    try {
      const managed = await githubApi('/api/managed-workspaces', { userId: expectedUserId });
      if (!isCurrentRequest()) return;
      setManagedWorkspaces(Array.isArray(managed) ? managed : []);
      const selectedWorkspace = (Array.isArray(managed) ? managed : [])
        .find((workspace) => workspace.id === expectedWorkspaceId);
      const ownerAccess = expectedWorkspaceId === personalWorkspaceId
        || selectedWorkspace?.accessRole === 'OWNER';
      setIsWorkspaceOwner(ownerAccess);
      if (!ownerAccess) setActiveTab('workspace');
      const connection = await githubApi('/api/github/connection', { userId: expectedUserId });
      if (!isCurrentRequest()) return;
      const nextConnectionStatus = String(connection.status || (connection.connected ? 'CONNECTED' : 'DISCONNECTED')).toUpperCase();
      setConnectionStatus(nextConnectionStatus);
      const canUseConnection = Boolean(connection.connected)
        && !['INVALID', 'REVOKED', 'DISCONNECTED'].includes(nextConnectionStatus);
      setIsConnected(canUseConnection);
      const workspace = await githubApi(`/api/workspaces/${expectedWorkspaceId}/repositories`, {
        userId: expectedUserId,
      });
      if (!isCurrentRequest()) return;
      setWorkspaceRepositories(workspace || []);
      const available = canUseConnection && ownerAccess
        ? await githubApi('/api/github/repos/available', { userId: expectedUserId })
        : [];
      if (!isCurrentRequest()) return;
      setAvailableRepositories(available || []);
    } catch (requestError) {
      if (isCurrentRequest()) setError(requestError.message || 'Could not load repositories.');
    } finally {
      if (isCurrentRequest()) setIsLoading(false);
    }
  }, [isCurrentWorkspace, personalWorkspaceId, userId, workspaceId]);

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
      refreshSequence.current += 1;
    };
  }, []);

  useEffect(() => {
    let active = true;
    Promise.resolve().then(() => {
      if (active) refreshRepositories(userId, workspaceId);
    });
    return () => {
      active = false;
      refreshSequence.current += 1;
    };
  }, [refreshRepositories, userId, workspaceId]);

  const workspaceGithubIds = useMemo(
    () => new Set(workspaceRepositories.map((repo) => repo.githubRepoId)),
    [workspaceRepositories],
  );

  const visibleTab = isWorkspaceOwner ? activeTab : 'workspace';

  const filteredRepositories = useMemo(() => {
    const source = visibleTab === 'available'
      ? availableRepositories.filter((repo) => !workspaceGithubIds.has(repo.githubRepoId))
      : workspaceRepositories;
    return source.filter((repo) => {
      const matchesSearch = repo.fullName.toLowerCase().includes(search.trim().toLowerCase());
      const matchesVisibility = visibility === 'all'
        || (visibility === 'public' && !repo.privateRepo)
        || (visibility === 'private' && repo.privateRepo);
      return matchesSearch && matchesVisibility;
    });
  }, [visibleTab, availableRepositories, search, visibility, workspaceGithubIds, workspaceRepositories]);

  function toggleSelection(repoId) {
    setSelectedIds((current) => current.includes(repoId)
      ? current.filter((id) => id !== repoId)
      : [...current, repoId]);
    setMessage('');
  }

  async function addSelectedRepositories() {
    const operationUserId = userId;
    const operationWorkspaceId = workspaceId;
    const repositoryIds = [...selectedIds];
    if (!repositoryIds.length) {
      setMessage('Select at least one repository.');
      return;
    }
    setIsAdding(true);
    setError('');
    setMessage('');
    try {
      await githubApi(`/api/workspaces/${operationWorkspaceId}/repositories`, {
        method: 'POST',
        userId: operationUserId,
        body: { githubRepoIds: repositoryIds },
      });
      if (!isCurrentWorkspace(operationUserId, operationWorkspaceId)) return;
      setSelectedIds([]);
      setMessage('Selected repositories added to workspace.');
      await refreshRepositories(operationUserId, operationWorkspaceId);
    } catch (requestError) {
      if (isCurrentWorkspace(operationUserId, operationWorkspaceId)) {
        setError(requestError.message || 'Could not add repositories to the workspace.');
      }
    } finally {
      if (isCurrentWorkspace(operationUserId, operationWorkspaceId)) setIsAdding(false);
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
    const operationUserId = userId;
    const operationWorkspaceId = workspaceId;
    setSyncingIds((current) => [...current, repository.id]);
    setSyncErrors((current) => ({ ...current, [repository.id]: '' }));
    setError('');
    try {
      const result = await githubApi(`/api/repositories/${repository.id}/sync`, {
        method: 'POST',
        body: {},
        userId: operationUserId,
      });
      if (!isCurrentWorkspace(operationUserId, operationWorkspaceId)) return;
      setWorkspaceRepositories((current) => current.map((repo) => repo.id === repository.id
        ? { ...repo, status: 'CONNECTED', lastSyncedAt: result.syncedAt || new Date().toISOString() }
        : repo));
      setMessage(`${repository.fullName} synchronized.`);
    } catch (requestError) {
      if (!isCurrentWorkspace(operationUserId, operationWorkspaceId)) return;
      const detail = requestError.retryAfter
        ? `${requestError.message} Retry after ${requestError.retryAfter} seconds.`
        : requestError.message || 'Repository synchronization failed.';
      setSyncErrors((current) => ({ ...current, [repository.id]: detail }));
    } finally {
      if (isCurrentWorkspace(operationUserId, operationWorkspaceId)) {
        setSyncingIds((current) => current.filter((id) => id !== repository.id));
      }
    }
  }

  async function removeFromWorkspace(repository) {
    const operationUserId = userId;
    const operationWorkspaceId = workspaceId;
    setError('');
    try {
      await githubApi(`/api/repositories/${repository.id}`, {
        method: 'DELETE', userId: operationUserId,
      });
      if (!isCurrentWorkspace(operationUserId, operationWorkspaceId)) return;
      setWorkspaceRepositories((current) => current.filter((repo) => repo.id !== repository.id));
      setMessage(`${repository.fullName} removed from workspace.`);
    } catch (requestError) {
      if (isCurrentWorkspace(operationUserId, operationWorkspaceId)) {
        setError(requestError.message || 'Could not remove repository.');
      }
    }
  }

  async function reassignRepository(repository) {
    const operationUserId = userId;
    const operationWorkspaceId = workspaceId;
    const targetWorkspaceId = reassignmentTargets[repository.id];
    if (!targetWorkspaceId) return;
    setError('');
    setReassigningIds((current) => [...current, repository.id]);
    try {
      await githubApi(`/api/workspaces/${encodeURIComponent(targetWorkspaceId)}/repositories/${repository.id}`, {
        method: 'PUT',
        userId: operationUserId,
      });
      if (!isCurrentWorkspace(operationUserId, operationWorkspaceId)) return;
      setWorkspaceRepositories((current) => current.filter((repo) => repo.id !== repository.id));
      setMessage(`${repository.fullName} moved to the selected workspace.`);
    } catch (requestError) {
      if (isCurrentWorkspace(operationUserId, operationWorkspaceId)) {
        setError(requestError.message || 'Could not move repository to the selected workspace.');
      }
    } finally {
      if (isCurrentWorkspace(operationUserId, operationWorkspaceId)) {
        setReassigningIds((current) => current.filter((id) => id !== repository.id));
      }
    }
  }

  const syncedCount = isConnected
    ? workspaceRepositories.filter((repo) => (
      repo.lastSyncedAt && !['DISCONNECTED', 'INVALID', 'REVOKED'].includes(String(repo.status || '').toUpperCase())
    )).length
    : 0;

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
                <p>{connectionStatus === 'INVALID'
                  ? 'GitHub authorization is invalid. Reconnect to continue.'
                  : connectionStatus === 'REVOKED'
                    ? 'GitHub authorization was revoked. Reconnect to continue.'
                    : isConnected ? 'Connected to GitHub.' : 'GitHub is not connected.'}</p>
              </div>
              <span className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`} role="status">
                <span className="status-dot" aria-hidden="true" />
                {connectionStatus === 'INVALID' ? 'Invalid'
                  : connectionStatus === 'REVOKED' ? 'Revoked'
                    : isConnected ? 'Connected' : 'Disconnected'}
              </span>
              {!isConnected && (
                <button type="button" onClick={connectGitHub}>
                  {['INVALID', 'REVOKED'].includes(connectionStatus) ? 'Reconnect GitHub' : 'Connect GitHub'}
                </button>
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

            <div className="repository-toolbar">
              <label htmlFor="repository-workspace">Workspace</label>
              <select id="repository-workspace" value={workspaceId}
                onChange={(event) => {
                  const nextWorkspaceId = event.target.value;
                  const nextWorkspace = managedWorkspaces.find((workspace) => workspace.id === nextWorkspaceId);
                  selectedWorkspaceContext.current = { userId, workspaceId: nextWorkspaceId };
                  refreshSequence.current += 1;
                  setWorkspaceId(nextWorkspaceId);
                  setIsWorkspaceOwner(nextWorkspaceId === personalWorkspaceId
                    || nextWorkspace?.accessRole === 'OWNER');
                  if (nextWorkspaceId !== personalWorkspaceId && nextWorkspace?.accessRole !== 'OWNER') {
                    setActiveTab('workspace');
                  }
                  setSelectedIds([]);
                  setReassignmentTargets({});
                  setWorkspaceRepositories([]);
                  setAvailableRepositories([]);
                  setSyncErrors({});
                  setSyncingIds([]);
                  setReassigningIds([]);
                  setIsAdding(false);
                  setIsLoading(true);
                  setError('');
                  setMessage('');
                }}>
                <option value={personalWorkspaceId}>Personal workspace</option>
                {managedWorkspaces.map((workspace) => (
                  <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
                ))}
              </select>
            </div>

            <div className="repository-tabs">
              {isWorkspaceOwner && (
                <button type="button" className={visibleTab === 'available' ? 'active' : ''} onClick={() => setActiveTab('available')}>
                  Available repositories
                </button>
              )}
              <button type="button" className={activeTab === 'workspace' ? 'active' : ''} onClick={() => setActiveTab('workspace')}>
                Workspace ({workspaceRepositories.length})
              </button>
            </div>
            {!isWorkspaceOwner && <p role="status">Read-only workspace member access.</p>}

            <div className="repository-toolbar">
              <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search repositories..." aria-label="Search repositories" />
              <select value={visibility} onChange={(event) => setVisibility(event.target.value)} aria-label="Filter repositories by visibility">
                <option value="all">All repositories</option>
                <option value="public">Public</option>
                <option value="private">Private</option>
              </select>
            </div>

            {isWorkspaceOwner && visibleTab === 'available' && (
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
                  const inWorkspace = visibleTab === 'workspace';
                  const syncing = syncingIds.includes(repo.id);
                  const syncError = syncErrors[repo.id];
                  const repoStatus = String(repo.status || '').toUpperCase();
                  const repoConnectionInvalid = ['INVALID', 'REVOKED'].includes(repoStatus);
                  const syncStatus = !isConnected
                    ? {
                      className: 'disconnected',
                      label: connectionStatus === 'INVALID' ? 'Invalid'
                        : connectionStatus === 'REVOKED' ? 'Revoked' : 'Disconnected',
                    }
                    : repoConnectionInvalid
                      ? { className: 'disconnected', label: repoStatus === 'INVALID' ? 'Invalid' : 'Revoked' }
                      : syncing
                        ? { className: 'syncing', label: 'Syncing…' }
                        : syncError || repoStatus === 'ERROR'
                          ? { className: 'failed', label: 'Sync failed' }
                          : repo.lastSyncedAt && repoStatus !== 'DISCONNECTED'
                            ? { className: 'synced', label: 'Synced' }
                            : { className: 'not-synced', label: 'Not synced' };
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
                          <span className={`sync-status sync-${syncStatus.className}`}>
                            {syncStatus.label}
                          </span>
                          {repo.lastSyncedAt && <p className="sync-last-time">Last synced: {new Date(repo.lastSyncedAt).toLocaleString()}</p>}
                          {syncError && <p className="sync-error" role="alert">{syncError}</p>}
                        </div>
                        <div className="sync-actions">
                          {inWorkspace && isWorkspaceOwner && (
                            <button type="button" disabled={syncing || !isConnected} onClick={() => syncRepository(repo)}>
                              {syncing ? 'Syncing…' : !isConnected ? 'Reconnect to sync' : syncError ? 'Retry sync' : 'Sync now'}
                            </button>
                          )}
                          {inWorkspace && (
                            <button type="button" className="sync-secondary-button" aria-expanded={activityRepoId === repo.id}
                              onClick={() => setActivityRepoId((current) => (current === repo.id ? null : repo.id))}>
                              {activityRepoId === repo.id ? 'Hide PRs & commits' : 'PRs & commits'}
                            </button>
                          )}
                          {inWorkspace && isWorkspaceOwner && (
                            <button type="button" className="sync-secondary-button" onClick={() => removeFromWorkspace(repo)}>
                              Remove
                            </button>
                          )}
                          {inWorkspace && isWorkspaceOwner && (managedWorkspaces.length > 0 || workspaceId !== personalWorkspaceId) && (
                            <>
                              <select aria-label={`Move ${repo.fullName} to workspace`}
                                value={reassignmentTargets[repo.id] || ''}
                                onChange={(event) => setReassignmentTargets((current) => ({
                                  ...current, [repo.id]: event.target.value,
                                }))}>
                                <option value="">Move to workspace…</option>
                                {workspaceId !== personalWorkspaceId && (
                                  <option value={personalWorkspaceId}>Personal workspace</option>
                                )}
                                {managedWorkspaces.filter((workspace) => workspace.id !== workspaceId).map((workspace) => (
                                  <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
                                ))}
                              </select>
                              <button type="button" className="sync-secondary-button"
                                disabled={!reassignmentTargets[repo.id] || reassigningIds.includes(repo.id)}
                                onClick={() => reassignRepository(repo)}>
                                {reassigningIds.includes(repo.id) ? 'Moving…' : 'Move'}
                              </button>
                            </>
                          )}
                        </div>
                        {inWorkspace && activityRepoId === repo.id && (
                          // key: reload after each sync, which also backfills pull requests and commits
                          <RepositoryActivity key={`${repo.id}-${repo.lastSyncedAt}`} repository={repo} userId={userId} />
                        )}
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



