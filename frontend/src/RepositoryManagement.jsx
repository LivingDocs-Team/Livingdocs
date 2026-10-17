
import { useMemo, useState } from 'react';
import './App.css';

const SAMPLE_REPOSITORIES = [
  {
    githubRepoId: 1001,
    fullName: 'demo-user/livingdocs',
    privateRepo: false,
    defaultBranch: 'main',
    htmlUrl: 'https://github.com/',
  },
  {
    githubRepoId: 1002,
    fullName: 'demo-user/documentation',
    privateRepo: true,
    defaultBranch: 'main',
    htmlUrl: 'https://github.com/',
  },
  {
    githubRepoId: 1003,
    fullName: 'demo-user/react-components',
    privateRepo: false,
    defaultBranch: 'develop',
    htmlUrl: 'https://github.com/',
  },
  {
    githubRepoId: 1004,
    fullName: 'demo-user/project-notes',
    privateRepo: true,
    defaultBranch: 'main',
    htmlUrl: 'https://github.com/',
  },
];

const INITIAL_SYNC_STATE = {
  status: 'not-synced',
  lastSynced: null,
  error: '',
};

export default function RepositoryManagement() {
  const [search, setSearch] = useState('');
  const [visibility, setVisibility] = useState('all');
  const [selectedIds, setSelectedIds] = useState([]);
  const [workspaceIds, setWorkspaceIds] = useState([]);
  const [activeTab, setActiveTab] = useState('available');
  const [message, setMessage] = useState('');
  const [syncStates, setSyncStates] = useState({});
  const [isConnected, setIsConnected] = useState(true);

  const filteredRepositories = useMemo(() => {
    return SAMPLE_REPOSITORIES.filter((repo) => {
      const matchesSearch = repo.fullName
        .toLowerCase()
        .includes(search.trim().toLowerCase());

      const matchesVisibility =
        visibility === 'all' ||
        (visibility === 'public' && !repo.privateRepo) ||
        (visibility === 'private' && repo.privateRepo);

      const matchesTab =
        activeTab === 'available' ||
        workspaceIds.includes(repo.githubRepoId);

      return matchesSearch && matchesVisibility && matchesTab;
    });
  }, [search, visibility, activeTab, workspaceIds]);

  function getSyncState(repoId) {
    return syncStates[repoId] || INITIAL_SYNC_STATE;
  }

  function updateSyncState(repoId, nextState) {
    setSyncStates((current) => ({
      ...current,
      [repoId]: {
        ...getSyncState(repoId),
        ...nextState,
      },
    }));
  }

  function toggleSelection(repoId) {
    setSelectedIds((current) =>
      current.includes(repoId)
        ? current.filter((id) => id !== repoId)
        : [...current, repoId]
    );
    setMessage('');
  }

  function addSelectedRepositories() {
    if (selectedIds.length === 0) {
      setMessage('Please select at least one repository.');
      return;
    }

    const newIds = selectedIds.filter(
      (id) => !workspaceIds.includes(id)
    );

    if (newIds.length === 0) {
      setMessage('Selected repositories are already in the workspace.');
      return;
    }

    setWorkspaceIds((current) => [...current, ...newIds]);
    setSelectedIds([]);
    setMessage(
      `${newIds.length} repository/repositories added to workspace.`
    );
  }

  function removeFromWorkspace(repoId) {
    setWorkspaceIds((current) =>
      current.filter((id) => id !== repoId)
    );
    setSelectedIds((current) =>
      current.filter((id) => id !== repoId)
    );
    setMessage('Repository removed from workspace.');
  }

  function syncRepository(repoId, simulateError = false) {
    if (!isConnected) {
      setMessage('Connect GitHub before synchronizing repositories.');
      return;
    }

    updateSyncState(repoId, {
      status: 'syncing',
      error: '',
    });
    setMessage('');

    // Demo only: simulate a synchronization request.
    window.setTimeout(() => {
      if (simulateError) {
        updateSyncState(repoId, {
          status: 'failed',
          error:
            'Demo sync error: unable to retrieve repository data. Please try again.',
        });
        return;
      }

      updateSyncState(repoId, {
        status: 'synced',
        lastSynced: new Date().toLocaleString(),
        error: '',
      });
    }, 1000);
  }

  const workspaceCount = workspaceIds.length;

  return (
    <main className="page">
      <section className="login-card repository-page">
        <h1>Repository Management</h1>
        <p className="subtitle">
          Manage GitHub repositories and synchronize your workspace.
        </p>

        <section className="sync-connection-panel">
          <div>
            <strong>GitHub connection</strong>
            <p>
              {isConnected
                ? 'Demo GitHub account: @demo-user'
                : 'GitHub is not connected.'}
            </p>
          </div>

          <span
            className={`connection-status ${
              isConnected ? 'connected' : 'disconnected'
            }`}
            role="status"
          >
            <span className="status-dot" aria-hidden="true" />
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>

          <button
            type="button"
            className={isConnected ? 'sync-secondary-button' : ''}
            onClick={() => {
              setIsConnected((current) => !current);
              setMessage('');
            }}
          >
            {isConnected ? 'Disconnect' : 'Connect GitHub'}
          </button>
        </section>

        <div className="repository-stats">
          <div className="repository-stat">
            <span>Available repositories</span>
            <strong>{SAMPLE_REPOSITORIES.length}</strong>
          </div>
          <div className="repository-stat">
            <span>Workspace repositories</span>
            <strong>{workspaceCount}</strong>
          </div>
          <div className="repository-stat">
            <span>Synced repositories</span>
            <strong>
              {workspaceIds.filter(
                (id) => getSyncState(id).status === 'synced'
              ).length}
            </strong>
          </div>
        </div>

        <div className="repository-tabs">
          <button
            type="button"
            className={activeTab === 'available' ? 'active' : ''}
            onClick={() => {
              setActiveTab('available');
              setMessage('');
            }}
          >
            Available repositories
          </button>

          <button
            type="button"
            className={activeTab === 'workspace' ? 'active' : ''}
            onClick={() => {
              setActiveTab('workspace');
              setMessage('');
            }}
          >
            Workspace ({workspaceCount})
          </button>
        </div>

        <div className="repository-toolbar">
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search repositories..."
            aria-label="Search repositories"
          />

          <select
            value={visibility}
            onChange={(event) => setVisibility(event.target.value)}
            aria-label="Filter repositories by visibility"
          >
            <option value="all">All repositories</option>
            <option value="public">Public</option>
            <option value="private">Private</option>
          </select>
        </div>

        {activeTab === 'available' && (
          <div className="repository-actions">
            <span>{selectedIds.length} selected</span>
            <button
              type="button"
              onClick={addSelectedRepositories}
            >
              Add selected to workspace
            </button>
          </div>
        )}

        {message && (
          <p className="repository-message" role="status">
            {message}
          </p>
        )}

        <p className="repository-result-count" role="status">
          Showing {filteredRepositories.length} repositories
        </p>

        {filteredRepositories.length === 0 ? (
          <div className="repository-empty">
            <h2>No repositories found</h2>
            <p>Try another search or filter.</p>
          </div>
        ) : (
          <ul className="repository-list">
            {filteredRepositories.map((repo) => {
              const inWorkspace = workspaceIds.includes(
                repo.githubRepoId
              );
              const sync = getSyncState(repo.githubRepoId);

              return (
                <li
                  className="repository-item repository-sync-item"
                  key={repo.githubRepoId}
                >
                  {activeTab === 'available' && (
                    <input
                      type="checkbox"
                      aria-label={`Select ${repo.fullName}`}
                      checked={selectedIds.includes(repo.githubRepoId)}
                      onChange={() =>
                        toggleSelection(repo.githubRepoId)
                      }
                    />
                  )}

                  <div className="repository-info">
                    <h2>{repo.fullName}</h2>

                    <div className="repository-meta">
                      <span>
                        {repo.privateRepo ? 'Private' : 'Public'}
                      </span>
                      <span>Branch: {repo.defaultBranch}</span>
                      {inWorkspace && (
                        <span>Added to workspace</span>
                      )}
                    </div>

                    <div className="sync-details">
                      <span className={`sync-status sync-${sync.status}`}>
                        {sync.status === 'not-synced' && 'Not synced'}
                        {sync.status === 'syncing' && 'Syncing…'}
                        {sync.status === 'synced' && 'Synced'}
                        {sync.status === 'failed' && 'Sync failed'}
                      </span>

                      {sync.lastSynced && (
                        <p className="sync-last-time">
                          Last synced: {sync.lastSynced}
                        </p>
                      )}

                      {sync.error && (
                        <p className="sync-error" role="alert">
                          {sync.error}
                        </p>
                      )}
                    </div>

                    <div className="sync-actions">
                      <button
                        type="button"
                        disabled={
                          !isConnected || sync.status === 'syncing'
                        }
                        onClick={() =>
                          syncRepository(repo.githubRepoId)
                        }
                      >
                        {sync.status === 'failed'
                          ? 'Retry sync'
                          : sync.status === 'syncing'
                            ? 'Syncing…'
                            : 'Sync now'}
                      </button>

                      {sync.status !== 'syncing' && (
                        <button
                          type="button"
                          className="sync-secondary-button"
                          disabled={!isConnected}
                          onClick={() =>
                            syncRepository(repo.githubRepoId, true)
                          }
                        >
                          Test sync error
                        </button>
                      )}

                      {activeTab === 'workspace' && (
                        <button
                          type="button"
                          className="sync-secondary-button"
                          onClick={() =>
                            removeFromWorkspace(repo.githubRepoId)
                          }
                        >
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

        <p className="repository-disclaimer">
          Demo mode: GitHub connection and synchronization are simulated.
          No real GitHub API, OAuth, or backend is used. Changes are kept
          in frontend state only.
        </p>
      </section>
    </main>
  );
}
