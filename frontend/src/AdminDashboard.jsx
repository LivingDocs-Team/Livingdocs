import { useEffect, useState } from 'react';
import './App.css';
import { csrfHeaders } from './csrf';
import { apiErrorMessage } from './errorMessages';

// LD-316: Administration & Dashboard interface (LD-317 .. LD-321).

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const SYSTEM_ROLES = ['DEVELOPER', 'STAFF', 'MANAGER', 'TECHNICAL_LEAD', 'ADMINISTRATOR'];
const TABS = [
  ['users', 'Users & roles'],
  ['workspaces', 'Workspaces & repositories'],
  ['config', 'System configuration'],
  ['health', 'Health & monitoring'],
  ['audit', 'Audit & analytics'],
  ['notifications', 'Notifications'],
];

const ANALYTICS_RANGES = [
  ['24h', 'Last 24 hours', 24 * 60 * 60 * 1000],
  ['7d', 'Last 7 days', 7 * 24 * 60 * 60 * 1000],
  ['30d', 'Last 30 days', 30 * 24 * 60 * 60 * 1000],
];

const EVENT_LABELS = {
  REPOSITORY_CONNECTED: 'Repository connected',
  DOCUMENT_SUBMITTED: 'Document submitted for review',
  DOCUMENT_APPROVED: 'Document approved',
  DOCUMENT_REJECTED: 'Document rejected',
  AI_JOB_COMPLETED: 'AI generation job completed',
  AI_JOB_FAILED: 'AI generation job failed',
};

async function adminApi(path, { method = 'GET', body } = {}) {
  let response;
  try {
    const headers = body === undefined ? {} : { 'Content-Type': 'application/json' };
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: method === 'GET' ? headers : await csrfHeaders(headers, API_BASE_URL),
      credentials: 'include',
      signal: AbortSignal.timeout(60000),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    throw new Error('Could not connect to the LivingDocs backend.', { cause: error });
  }
  const data = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event('livingdocs:unauthenticated'));
    throw new Error(apiErrorMessage(undefined, response.status, data?.message));
  }
  return data;
}

function useApi(path) {
  const [state, setState] = useState({ data: null, error: '', loading: true });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.resolve()
      .then(() => {
        if (cancelled) return null;
        setState((current) => ({ ...current, loading: true, error: '' }));
        return adminApi(path);
      })
      .then((data) => {
        if (!cancelled) setState({ data, error: '', loading: false });
      })
      .catch((requestError) => {
        if (!cancelled) setState({ data: null, error: requestError.message, loading: false });
      });
    return () => { cancelled = true; };
  }, [path, version]);

  return { ...state, reload: () => setVersion((value) => value + 1) };
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : '—';
}

function Feedback({ loading, error, notice }) {
  return (
    <>
      {loading && <p role="status">Loading…</p>}
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
    </>
  );
}

// LD-317: users, roles and permissions
function UsersPanel({ currentUserId }) {
  const [filters, setFilters] = useState({ search: '', role: '', active: '' });
  const [draftSearch, setDraftSearch] = useState('');
  const [page, setPage] = useState(0);
  const [notice, setNotice] = useState('');
  const [actionError, setActionError] = useState('');
  const params = new URLSearchParams({ page: String(page), size: '10' });
  Object.entries(filters).forEach(([key, value]) => { if (value) params.set(key, value); });
  const { data, error, loading, reload } = useApi(`/api/admin/users?${params}`);

  function changeFilter(name, value) {
    setFilters((current) => ({ ...current, [name]: value }));
    setPage(0);
  }

  async function updateUser(user, path, body, message) {
    setNotice('');
    setActionError('');
    try {
      await adminApi(`/api/admin/users/${user.id}${path}`, { method: 'PATCH', body });
      setNotice(message);
      reload();
    } catch (requestError) {
      setActionError(requestError.message);
    }
  }

  function toggleStatus(user) {
    if (user.active && !window.confirm(`Disable ${user.email}? They will no longer be able to sign in.`)) return;
    updateUser(
      user,
      '/status',
      { active: !user.active },
      `${user.email} ${user.active ? 'disabled' : 'enabled'}.`,
    );
  }

  return (
    <section className="admin-section">
      <h2>Users</h2>
      <form
        className="admin-toolbar"
        onSubmit={(event) => { event.preventDefault(); changeFilter('search', draftSearch.trim()); }}
      >
        <input
          aria-label="Search users"
          placeholder="Search by name, username or email"
          value={draftSearch}
          onChange={(event) => setDraftSearch(event.target.value)}
        />
        <select
          aria-label="Filter by role"
          value={filters.role}
          onChange={(event) => changeFilter('role', event.target.value)}
        >
          <option value="">All roles</option>
          {SYSTEM_ROLES.map((role) => <option key={role} value={role}>{role}</option>)}
        </select>
        <select
          aria-label="Filter by status"
          value={filters.active}
          onChange={(event) => changeFilter('active', event.target.value)}
        >
          <option value="">All statuses</option>
          <option value="true">Active</option>
          <option value="false">Disabled</option>
        </select>
        <button type="submit">Search</button>
      </form>
      <Feedback loading={loading} error={error || actionError} notice={notice} />
      {data && (
        <>
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr><th>User</th><th>Email</th><th>Role</th><th>Status</th><th>Created</th><th>Action</th></tr>
              </thead>
              <tbody>
                {(data.content || []).map((user) => {
                  const isSelf = String(user.id) === String(currentUserId);
                  const roleOptions = SYSTEM_ROLES.includes(user.role) ? SYSTEM_ROLES : [user.role, ...SYSTEM_ROLES];
                  return (
                    <tr key={user.id}>
                      <td>{user.firstName} {user.lastName} <small>@{user.username}</small></td>
                      <td>{user.email}</td>
                      <td>
                        <select
                          aria-label={`Role for ${user.email}`}
                          value={user.role}
                          disabled={isSelf}
                          onChange={(event) => updateUser(
                            user,
                            '/role',
                            { role: event.target.value },
                            `Role of ${user.email} changed to ${event.target.value}.`,
                          )}
                        >
                          {roleOptions.map((role) => <option key={role} value={role}>{role}</option>)}
                        </select>
                      </td>
                      <td>
                        <span className={`admin-pill ${user.active ? 'up' : 'down'}`}>
                          {user.active ? 'Active' : 'Disabled'}
                        </span>
                      </td>
                      <td>{formatDate(user.createdAt)}</td>
                      <td>
                        <button type="button" disabled={isSelf} onClick={() => toggleStatus(user)}>
                          {user.active ? 'Disable' : 'Enable'}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="admin-pager">
            <button type="button" disabled={data.first} onClick={() => setPage(page - 1)}>Previous</button>
            <span>Page {data.page + 1} of {Math.max(data.totalPages, 1)} · {data.totalElements} users</span>
            <button type="button" disabled={data.last} onClick={() => setPage(page + 1)}>Next</button>
          </div>
        </>
      )}
    </section>
  );
}

function RoleCard({ role, permissions, onSaved }) {
  const [selected, setSelected] = useState(role.permissions);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  function toggle(code) {
    setSelected((current) => (current.includes(code)
      ? current.filter((item) => item !== code)
      : [...current, code]));
    setMessage('');
  }

  async function save() {
    setMessage('');
    setError('');
    try {
      await adminApi(`/api/admin/roles/${encodeURIComponent(role.name)}/permissions`, {
        method: 'PUT',
        body: { permissionCodes: selected },
      });
      setMessage('Permissions saved.');
      onSaved();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  return (
    <details className="admin-role">
      <summary>
        <strong>{role.name}</strong> <span>{role.description}</span>
        <span className="admin-count">{role.permissions.length} permission(s)</span>
      </summary>
      <div className="admin-permissions">
        {permissions.map((permission) => (
          <label key={permission.code} title={permission.description}>
            <input
              type="checkbox"
              checked={selected.includes(permission.code)}
              onChange={() => toggle(permission.code)}
            />
            {permission.code}
          </label>
        ))}
      </div>
      <button type="button" onClick={save}>Save permissions</button>
      <Feedback error={error} notice={message} />
    </details>
  );
}

function RolesPanel() {
  const roles = useApi('/api/admin/roles');
  const permissions = useApi('/api/admin/permissions');
  return (
    <section className="admin-section">
      <h2>Roles & permissions</h2>
      <Feedback loading={roles.loading || permissions.loading} error={roles.error || permissions.error} />
      {roles.data && permissions.data && roles.data.map((role) => (
        <RoleCard key={role.name} role={role} permissions={permissions.data} onSaved={roles.reload} />
      ))}
    </section>
  );
}

// LD-318: system-wide workspaces and repositories administration
function WorkspaceMembersAdmin({ workspaceId, onChanged }) {
  const { data, error, loading, reload } = useApi(`/api/admin/workspaces/${encodeURIComponent(workspaceId)}/members`);
  const users = useApi('/api/admin/users?page=0&size=100&active=true');
  const [selectedUserId, setSelectedUserId] = useState('');
  const [notice, setNotice] = useState('');
  const [actionError, setActionError] = useState('');

  async function addMember(event) {
    event.preventDefault();
    if (!selectedUserId) return;
    setNotice('');
    setActionError('');
    try {
      await adminApi(`/api/admin/workspaces/${encodeURIComponent(workspaceId)}/members`, {
        method: 'POST',
        body: { userId: Number(selectedUserId) },
      });
      setSelectedUserId('');
      setNotice('Member added to workspace.');
      reload();
      onChanged();
    } catch (requestError) {
      setActionError(requestError.message);
    }
  }

  async function removeMember(userId) {
    setNotice('');
    setActionError('');
    try {
      await adminApi(`/api/admin/workspaces/${encodeURIComponent(workspaceId)}/members/${userId}`, {
        method: 'DELETE',
      });
      setNotice('Member removed from workspace.');
      reload();
      onChanged();
    } catch (requestError) {
      setActionError(requestError.message);
    }
  }

  const existingIds = new Set((data || []).map((member) => String(member.userId)));
  const candidateUsers = (users.data?.content || []).filter((u) => !existingIds.has(String(u.id)));

  return (
    <>
      <h3>Workspace members</h3>
      <form className="admin-toolbar" onSubmit={addMember}>
        <select
          aria-label="Select user to add"
          value={selectedUserId}
          onChange={(event) => setSelectedUserId(event.target.value)}
        >
          <option value="">Select active user…</option>
          {candidateUsers.map((user) => (
            <option key={user.id} value={user.id}>
              {user.firstName} {user.lastName} ({user.email})
            </option>
          ))}
        </select>
        <button type="submit" disabled={!selectedUserId}>Add member</button>
      </form>
      <Feedback loading={loading} error={error || actionError} notice={notice} />
      {data && (data.length === 0 ? <p className="admin-note">No members in this workspace.</p> : (
        <ul className="admin-list">
          {data.map((member) => (
            <li key={member.userId}>
              <span>{member.displayName || member.username} <small>@{member.username}</small></span>{' '}
              <button type="button" onClick={() => removeMember(member.userId)}>Remove</button>
            </li>
          ))}
        </ul>
      ))}
    </>
  );
}

function WorkspaceDetail({ workspace, isPersonal, onWorkspaceUpdated }) {
  const repositories = useApi(`/api/workspaces/${encodeURIComponent(workspace.id)}/repositories`);
  const [syncingIds, setSyncingIds] = useState([]);
  const [removingIds, setRemovingIds] = useState([]);
  const [notice, setNotice] = useState('');
  const [syncError, setSyncError] = useState('');
  const [editName, setEditName] = useState(workspace.name || '');
  const [editDescription, setEditDescription] = useState(workspace.description || '');
  const [savingMeta, setSavingMeta] = useState(false);

  async function saveWorkspaceMetadata(event) {
    event.preventDefault();
    setSavingMeta(true);
    setNotice('');
    setSyncError('');
    try {
      await adminApi(`/api/admin/workspaces/${encodeURIComponent(workspace.id)}`, {
        method: 'PUT',
        body: { name: editName, description: editDescription },
      });
      setNotice('Workspace details updated.');
      onWorkspaceUpdated();
    } catch (requestError) {
      setSyncError(requestError.message);
    } finally {
      setSavingMeta(false);
    }
  }

  async function sync(repository) {
    setNotice('');
    setSyncError('');
    setSyncingIds((current) => [...current, repository.id]);
    try {
      await adminApi(`/api/repositories/${repository.id}/sync`, { method: 'POST', body: {} });
      setNotice(`${repository.fullName} synchronized.`);
      repositories.reload();
    } catch (requestError) {
      setSyncError(`${repository.fullName}: ${requestError.message}`);
    } finally {
      setSyncingIds((current) => current.filter((id) => id !== repository.id));
    }
  }

  async function disconnectRepository(repository) {
    if (!window.confirm(`Remove ${repository.fullName} from this workspace?`)) return;
    setNotice('');
    setSyncError('');
    setRemovingIds((current) => [...current, repository.id]);
    try {
      await adminApi(`/api/repositories/${repository.id}`, { method: 'DELETE' });
      setNotice(`${repository.fullName} removed from workspace.`);
      repositories.reload();
    } catch (requestError) {
      setSyncError(`${repository.fullName}: ${requestError.message}`);
    } finally {
      setRemovingIds((current) => current.filter((id) => id !== repository.id));
    }
  }

  return (
    <>
      {!isPersonal && (
        <form className="admin-toolbar" onSubmit={saveWorkspaceMetadata}>
          <input
            aria-label="Workspace name"
            value={editName}
            onChange={(event) => setEditName(event.target.value)}
            required
          />
          <input
            aria-label="Workspace description"
            placeholder="Workspace description"
            value={editDescription}
            onChange={(event) => setEditDescription(event.target.value)}
          />
          <button type="submit" disabled={savingMeta}>
            {savingMeta ? 'Saving…' : 'Save workspace'}
          </button>
        </form>
      )}
      {workspace.ownerEmail && (
        <p className="admin-note">
          Owner: <strong>{workspace.ownerEmail}</strong> (@{workspace.ownerUsername}) · Members: {workspace.memberCount ?? 0}
        </p>
      )}
      <h3>Connected repositories</h3>
      <Feedback loading={repositories.loading} error={repositories.error || syncError} notice={notice} />
      {repositories.data && (repositories.data.length === 0 ? <p className="admin-note">No repositories connected.</p> : (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr><th>Repository</th><th>Branch</th><th>Visibility</th><th>Status</th><th>Last synced</th><th>Action</th></tr>
            </thead>
            <tbody>
              {repositories.data.map((repository) => (
                <tr key={repository.id}>
                  <td>{repository.fullName}</td>
                  <td>{repository.defaultBranch}</td>
                  <td>{repository.privateRepo ? 'Private' : 'Public'}</td>
                  <td>{repository.status}</td>
                  <td>{formatDate(repository.lastSyncedAt)}</td>
                  <td>
                    <button
                      type="button"
                      disabled={syncingIds.includes(repository.id)}
                      onClick={() => sync(repository)}
                    >
                      {syncingIds.includes(repository.id) ? 'Syncing…' : 'Sync'}
                    </button>{' '}
                    <button
                      type="button"
                      disabled={removingIds.includes(repository.id)}
                      onClick={() => disconnectRepository(repository)}
                    >
                      {removingIds.includes(repository.id) ? 'Removing…' : 'Remove'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      {!isPersonal && <WorkspaceMembersAdmin workspaceId={workspace.id} onChanged={onWorkspaceUpdated} />}
    </>
  );
}

function WorkspacesPanel({ userId }) {
  const personalId = `ws-${userId}`;
  const { data, error, loading, reload } = useApi('/api/admin/workspaces');
  const [selectedId, setSelectedId] = useState('');
  const [search, setSearch] = useState('');

  const managedWorkspaces = (data || []).filter((ws) => {
    if (!search.trim()) return true;
    const q = search.trim().toLowerCase();
    return (
      ws.name?.toLowerCase().includes(q)
      || ws.ownerEmail?.toLowerCase().includes(q)
      || ws.ownerUsername?.toLowerCase().includes(q)
    );
  });

  const workspaces = [
    ...managedWorkspaces.map((ws) => ({
      ...ws,
      label: `${ws.name} (${ws.ownerEmail || `Owner #${ws.ownerId}`})`,
    })),
    {
      id: personalId,
      name: 'Personal workspace',
      label: `Personal workspace (${personalId})`,
      ownerId: userId,
    },
  ];

  const activeId = selectedId && workspaces.some((ws) => ws.id === selectedId)
    ? selectedId
    : workspaces[0].id;
  const selected = workspaces.find((workspace) => workspace.id === activeId) || workspaces[0];

  return (
    <section className="admin-section">
      <h2>Workspaces & repositories</h2>
      <p className="admin-note">
        System-wide directory of managed workspaces, members and connected repositories.
      </p>
      <Feedback loading={loading} error={error} />
      <div className="admin-toolbar">
        <input
          aria-label="Filter workspaces"
          placeholder="Filter by workspace or owner"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <select
          aria-label="Workspace"
          value={selected.id}
          onChange={(event) => setSelectedId(event.target.value)}
        >
          {workspaces.map((workspace) => (
            <option key={workspace.id} value={workspace.id}>{workspace.label}</option>
          ))}
        </select>
      </div>
      <WorkspaceDetail
        key={selected.id}
        workspace={selected}
        isPersonal={selected.id === personalId}
        onWorkspaceUpdated={reload}
      />
    </section>
  );
}

// LD-319: system configuration
function ConfigPanel() {
  const config = useApi('/api/admin/system-config');
  const rules = useApi('/api/documentation/drift/severity-rules');
  const [retentionDraft, setRetentionDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  const [saveError, setSaveError] = useState('');

  const retentionValue = retentionDraft !== null
    ? retentionDraft
    : String(config.data?.audit?.retentionDays ?? 0);

  async function saveRetention(event) {
    event.preventDefault();
    setSaving(true);
    setNotice('');
    setSaveError('');
    try {
      const days = Number(retentionValue);
      if (!Number.isInteger(days) || days < 0 || days > 3650) {
        throw new Error('Audit retention days must be an integer between 0 and 3650.');
      }
      await adminApi('/api/admin/system-config', {
        method: 'PATCH',
        body: { auditRetentionDays: days },
      });
      setRetentionDraft(null);
      setNotice('System configuration saved.');
      config.reload();
    } catch (requestError) {
      setSaveError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="admin-section">
      <h2>System configuration</h2>
      <p className="admin-note">
        Manage operational platform parameters and review active integration and documentation drift settings.
      </p>
      <Feedback loading={config.loading} error={config.error || saveError} notice={notice} />

      {config.data && (
        <>
          <h3>Audit retention policy</h3>
          <form className="admin-toolbar" onSubmit={saveRetention}>
            <label htmlFor="audit-retention-days">Audit retention (days, 0 = keep forever)</label>
            <input
              id="audit-retention-days"
              aria-label="Audit retention days"
              type="number"
              min="0"
              max="3650"
              value={retentionValue}
              onChange={(event) => {
                setRetentionDraft(event.target.value);
                setNotice('');
              }}
            />
            <button type="submit" disabled={saving}>
              {saving ? 'Saving…' : 'Save configuration'}
            </button>
          </form>

          <h3>Security & integration runtime</h3>
          <dl className="admin-facts">
            <dt>Frontend URL</dt><dd>{config.data.security?.frontendUrl || '—'}</dd>
            <dt>Session cookie SameSite</dt><dd>{config.data.security?.sessionCookieSameSite || 'Lax'}</dd>
            <dt>Session cookie Secure</dt><dd>{config.data.security?.sessionCookieSecure ? 'Enabled' : 'Disabled'}</dd>
            <dt>GitHub OAuth2 client</dt><dd>{config.data.security?.githubOAuthConfigured ? 'Configured' : 'Not configured'}</dd>
            <dt>GitHub Integration URL</dt><dd>{config.data.integration?.githubIntegrationBaseUrl || '—'}</dd>
            <dt>Internal BFF secret</dt><dd>{config.data.integration?.internalSecretConfigured ? 'Configured' : 'Missing'}</dd>
            <dt>Integration timeouts</dt>
            <dd>
              Connect {config.data.integration?.connectTimeoutSeconds ?? '—'}s · Read {config.data.integration?.readTimeoutSeconds ?? '—'}s
            </dd>
            <dt>API base URL</dt><dd>{API_BASE_URL || 'Same origin (proxied)'}</dd>
          </dl>
        </>
      )}

      <h3>Documentation drift severity rules</h3>
      <Feedback loading={rules.loading} error={rules.error} />
      {rules.data?.levels && (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr><th>Level</th><th>Score band</th><th>Meaning</th><th>Recommended action</th></tr>
            </thead>
            <tbody>
              {rules.data.levels.map((lvl) => (
                <tr key={lvl.level}>
                  <td><strong>{String(lvl.level).toUpperCase()}</strong></td>
                  <td>{lvl.min_score} – {lvl.max_score ?? 100}</td>
                  <td>{lvl.meaning || '—'}</td>
                  <td>{lvl.action || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rules.data && (
        <details className="admin-role">
          <summary>Raw severity rule catalog (JSON)</summary>
          <pre className="admin-json">{JSON.stringify(rules.data, null, 2)}</pre>
        </details>
      )}
    </section>
  );
}

// LD-320: system health and monitoring via BFF health endpoint
async function probeHealth() {
  const started = performance.now();
  try {
    const response = await fetch(`${API_BASE_URL}/api/admin/health`, {
      credentials: 'include',
      signal: AbortSignal.timeout(15000),
    });
    const elapsedMs = Math.round(performance.now() - started);

    if (response.status === 401 || response.status === 403) {
      if (response.status === 401) {
        window.dispatchEvent(new Event('livingdocs:unauthenticated'));
      }
      return {
        authError: response.status === 401
          ? 'Authentication required to check service health (HTTP 401).'
          : 'Administrator access is required to check service health (HTTP 403).',
        services: [
          {
            id: 'bff-health',
            name: 'Administration Health BFF',
            status: 'auth_error',
            httpStatus: response.status,
            ms: elapsedMs,
            detail: response.status === 401 ? 'Unauthenticated (HTTP 401)' : 'Forbidden (HTTP 403)',
          },
        ],
      };
    }

    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const message = payload?.message || `Health endpoint returned HTTP ${response.status}`;
      return {
        authError: '',
        services: [
          {
            id: 'bff-health',
            name: 'Administration Health BFF',
            status: 'down',
            httpStatus: response.status,
            ms: elapsedMs,
            detail: message,
          },
        ],
      };
    }

    if (!payload || typeof payload !== 'object') {
      return {
        authError: '',
        services: [
          {
            id: 'bff-health',
            name: 'Administration Health BFF',
            status: 'down',
            httpStatus: response.status,
            ms: elapsedMs,
            detail: 'Invalid health payload',
          },
        ],
      };
    }

    if (Array.isArray(payload.services) && payload.services.length > 0) {
      return {
        authError: '',
        services: payload.services.map((svc, index) => {
          const httpOk = svc.httpStatus == null || (svc.httpStatus >= 200 && svc.httpStatus < 300);
          const payloadUp = String(svc.status || '').toUpperCase() === 'UP';
          return {
            id: svc.id || `service-${index}`,
            name: svc.name || svc.id || 'Service',
            status: httpOk && payloadUp ? 'up' : 'down',
            httpStatus: svc.httpStatus ?? response.status,
            ms: svc.latencyMs ?? elapsedMs,
            detail: svc.detail || (httpOk && payloadUp ? 'UP' : 'Unhealthy'),
          };
        }),
      };
    }

    const isUp = String(payload.status || '').toUpperCase() === 'UP';
    return {
      authError: '',
      services: [
        {
          id: 'backend',
          name: 'Backend API',
          status: isUp ? 'up' : 'down',
          httpStatus: response.status,
          ms: elapsedMs,
          detail: payload.status ? `Status: ${payload.status}` : 'Missing status field in payload',
        },
      ],
    };
  } catch {
    return {
      authError: '',
      services: [
        {
          id: 'bff-health',
          name: 'Administration Health BFF',
          status: 'down',
          httpStatus: null,
          ms: null,
          detail: 'No response from backend',
        },
      ],
    };
  }
}

function statusPillLabel(status) {
  if (status === 'up') return 'Up';
  if (status === 'auth_error') return 'Auth error';
  return 'Down';
}

function HealthPanel() {
  const [state, setState] = useState({ services: [], authError: '', checkedAt: null, loading: true });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.resolve()
      .then(() => {
        if (cancelled) return null;
        setState((current) => ({ ...current, loading: true }));
        return probeHealth();
      })
      .then((outcome) => {
        if (!cancelled && outcome) {
          setState({
            services: outcome.services,
            authError: outcome.authError,
            checkedAt: new Date(),
            loading: false,
          });
        }
      });
    return () => { cancelled = true; };
  }, [version]);

  return (
    <section className="admin-section">
      <h2>System health</h2>
      <p className="admin-note">
        Service availability checked via Backend BFF (HTTP status and health payload verified).
      </p>
      <div className="admin-toolbar">
        <button type="button" disabled={state.loading} onClick={() => setVersion((value) => value + 1)}>
          {state.loading ? 'Checking…' : 'Check again'}
        </button>
        {state.checkedAt && <span className="admin-note">Last checked {formatDate(state.checkedAt)}</span>}
      </div>
      {state.authError && <p role="alert">{state.authError}</p>}
      {state.services.length > 0 && (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr><th>Service</th><th>Status</th><th>HTTP</th><th>Response</th><th>Detail</th></tr>
            </thead>
            <tbody>
              {state.services.map((service) => (
                <tr key={service.id}>
                  <td>{service.name}</td>
                  <td>
                    <span className={`admin-pill ${service.status === 'up' ? 'up' : 'down'}`}>
                      {statusPillLabel(service.status)}
                    </span>
                  </td>
                  <td>{service.httpStatus ?? '—'}</td>
                  <td>{service.ms === null ? '—' : `${service.ms} ms`}</td>
                  <td>{service.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// LD-321: system analytics, administrative audit log and notification policies
function SystemAnalyticsSection() {
  const [rangeKey, setRangeKey] = useState('7d');
  const [anchorMs, setAnchorMs] = useState(() => Date.now());
  const selectedRange = ANALYTICS_RANGES.find(([key]) => key === rangeKey) || ANALYTICS_RANGES[1];
  const fromIso = new Date(anchorMs - selectedRange[2]).toISOString();
  const toIso = new Date(anchorMs).toISOString();
  const query = new URLSearchParams({ from: fromIso, to: toIso });
  const { data, error, loading } = useApi(`/api/admin/system-analytics?${query}`);

  return (
    <section className="admin-section">
      <h2>System analytics</h2>
      <div className="admin-toolbar">
        <select
          aria-label="Analytics time range"
          value={rangeKey}
          onChange={(event) => {
            setRangeKey(event.target.value);
            setAnchorMs(Date.now());
          }}
        >
          {ANALYTICS_RANGES.map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
        <button type="button" onClick={() => setAnchorMs(Date.now())}>Refresh metrics</button>
      </div>
      <Feedback loading={loading} error={error} />
      {data && (
        <>
          <div className="admin-stats">
            <div className="admin-stat">
              <span>Repositories connected</span>
              <strong>{data.repositoriesCreated}</strong>
            </div>
            <div className="admin-stat">
              <span>Documents created</span>
              <strong>{data.documentsCreated}</strong>
            </div>
            <div className="admin-stat">
              <span>AI jobs completed</span>
              <strong>{data.aiJobs?.completed ?? 0}</strong>
            </div>
            <div className="admin-stat">
              <span>AI jobs failed</span>
              <strong>{data.aiJobs?.failed ?? 0}</strong>
            </div>
            <div className="admin-stat">
              <span>Admin audit events</span>
              <strong>{data.audit?.administration ?? 0}</strong>
            </div>
            <div className="admin-stat">
              <span>Workflow audit events</span>
              <strong>{data.audit?.documentWorkflow ?? 0}</strong>
            </div>
            <div className="admin-stat">
              <span>Document version events</span>
              <strong>{data.audit?.documentVersion ?? 0}</strong>
            </div>
          </div>
          {data.aiJobs?.observedSince && (
            <p className="admin-note">
              AI job metrics cover current AI process since {formatDate(data.aiJobs.observedSince)}.
            </p>
          )}
        </>
      )}
    </section>
  );
}

function describeAuditTarget(entry) {
  if (entry.targetId != null) return `User #${entry.targetId}`;
  if (entry.targetRole) return `Role ${entry.targetRole}`;
  if (entry.targetEvent) return `Event ${entry.targetEvent}`;
  return '—';
}

function AuditPanel() {
  const [page, setPage] = useState(0);
  const { data, error, loading } = useApi(`/api/admin/users/audit?page=${page}&size=20`);

  return (
    <>
      <SystemAnalyticsSection />
      <section className="admin-section">
        <h2>Administrative audit log{data ? ` (${data.totalElements})` : ''}</h2>
        <p className="admin-note">
          Records user account updates, role and permission mutations, and notification policy changes.
        </p>
        <Feedback loading={loading} error={error} />
        {data && (data.content || []).length === 0 && <p className="admin-note">No audit entries recorded yet.</p>}
        {data && (data.content || []).length > 0 && (
          <>
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr><th>Timestamp</th><th>Action</th><th>Actor</th><th>Target</th><th>Details</th></tr>
                </thead>
                <tbody>
                  {data.content.map((entry) => (
                    <tr key={entry.id}>
                      <td>{formatDate(entry.occurredAt)}</td>
                      <td><strong>{entry.action}</strong></td>
                      <td>User #{entry.actorId}</td>
                      <td>{describeAuditTarget(entry)}</td>
                      <td>
                        {entry.previousValue || entry.newValue
                          ? `${entry.previousValue || '—'} → ${entry.newValue || '—'}`
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="admin-pager">
              <button type="button" disabled={page <= 0} onClick={() => setPage(page - 1)}>Previous</button>
              <span>Page {data.page + 1} of {Math.max(data.totalPages, 1)}</span>
              <button
                type="button"
                disabled={data.page + 1 >= Math.max(data.totalPages, 1)}
                onClick={() => setPage(page + 1)}
              >
                Next
              </button>
            </div>
          </>
        )}
      </section>
    </>
  );
}

function NotificationPolicyRow({ event, existing, onSaved }) {
  const [recipientsText, setRecipientsText] = useState((existing?.recipients || []).join(', '));
  const [enabled, setEnabled] = useState(existing ? Boolean(existing.enabled) : true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  async function handleSave(submitEvent) {
    submitEvent.preventDefault();
    setNotice('');
    setError('');
    const recipients = recipientsText
      .split(/[\s,;]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    if (recipients.length === 0) {
      setError('Enter at least one recipient email address.');
      return;
    }
    setSaving(true);
    try {
      await adminApi(`/api/admin/notification-policies/${encodeURIComponent(event)}`, {
        method: 'PUT',
        body: { recipients, enabled },
      });
      setNotice(`Policy for ${event} saved.`);
      onSaved();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    setNotice('');
    setError('');
    setSaving(true);
    try {
      await adminApi(`/api/admin/notification-policies/${encodeURIComponent(event)}`, {
        method: 'DELETE',
      });
      setRecipientsText('');
      setEnabled(true);
      setNotice(`Policy for ${event} deleted.`);
      onSaved();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <details className="admin-role" open={Boolean(existing)}>
      <summary>
        <strong>{EVENT_LABELS[event] || event}</strong> <span>({event})</span>
        <span className="admin-count">
          {existing ? (existing.enabled ? 'Enabled' : 'Disabled') : 'Not configured'}
        </span>
      </summary>
      <form onSubmit={handleSave}>
        <div className="admin-toolbar">
          <input
            aria-label={`Recipients for ${event}`}
            placeholder="admin@example.com, ops@example.com"
            value={recipientsText}
            onChange={(e) => {
              setRecipientsText(e.target.value);
              setNotice('');
            }}
          />
          <label>
            <input
              type="checkbox"
              aria-label={`Enable ${event}`}
              checked={enabled}
              onChange={(e) => {
                setEnabled(e.target.checked);
                setNotice('');
              }}
            />
            Enabled
          </label>
          <button type="submit" disabled={saving}>Save policy</button>
          {existing && (
            <button type="button" disabled={saving} onClick={handleDelete}>Delete policy</button>
          )}
        </div>
        {existing?.updatedAt && (
          <p className="admin-note">Last updated {formatDate(existing.updatedAt)}</p>
        )}
        <Feedback error={error} notice={notice} />
      </form>
    </details>
  );
}

function NotificationPoliciesPanel() {
  const { data, error, loading, reload } = useApi('/api/admin/notification-policies');
  const events = data?.supportedEvents || Object.keys(EVENT_LABELS);
  const policiesByEvent = new Map((data?.policies || []).map((policy) => [policy.event, policy]));

  return (
    <section className="admin-section">
      <h2>Notification policies</h2>
      <p className="admin-note">
        Configure system-wide email recipients and delivery rules for platform events.
      </p>
      <Feedback loading={loading} error={error} />
      {data && events.map((event) => {
        const existing = policiesByEvent.get(event) || null;
        return (
          <NotificationPolicyRow
            key={`${event}-${existing?.updatedAt || 'none'}`}
            event={event}
            existing={existing}
            onSaved={reload}
          />
        );
      })}
    </section>
  );
}

// Each Administrator screen of the role-based shell opens the dashboard on its own section; the tabs
// stay available to move between the sections that belong to the same page.
const TAB_BY_SCREEN = {
  'user-management': 'users',
  'workspace-administration': 'workspaces',
  'system-configuration': 'config',
  monitoring: 'health',
  'notification-policies': 'notifications',
};

function AdministrationTabs({ userId, initialTab }) {
  const [tab, setTab] = useState(initialTab);

  return (
    <div className="admin-dashboard">
      <h1>Administration</h1>
      <p className="admin-subtitle">Manage users, workspaces, system settings and monitoring.</p>
      <div className="admin-tabs" role="tablist" aria-label="Administration sections">
        {TABS.map(([id, label]) => (
          <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        {tab === 'users' && (
          <>
            <UsersPanel currentUserId={userId} />
            <RolesPanel />
          </>
        )}
        {tab === 'workspaces' && <WorkspacesPanel userId={userId} />}
        {tab === 'config' && <ConfigPanel />}
        {tab === 'health' && <HealthPanel />}
        {tab === 'audit' && <AuditPanel />}
        {tab === 'notifications' && <NotificationPoliciesPanel />}
      </div>
    </div>
  );
}

export default function AdminDashboard({ userId, node }) {
  // The shell keeps this component mounted while the Administrator moves between admin screens, so the
  // screen key resets the selected tab.
  return <AdministrationTabs key={node?.key} userId={userId} initialTab={TAB_BY_SCREEN[node?.key] || 'users'} />;
}
