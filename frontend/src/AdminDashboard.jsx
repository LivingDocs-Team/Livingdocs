import { useEffect, useState } from 'react';
import './App.css';
import { csrfHeaders } from './csrf';
import { apiErrorMessage } from './errorMessages';
import NotificationPreferences from './NotificationPreferences';

// LD-316: Administration & Dashboard interface (LD-317 .. LD-321).
// It only calls endpoints that already exist; sections whose backend API is missing say so.

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
const SYSTEM_ROLES = ['DEVELOPER', 'STAFF', 'MANAGER', 'TECHNICAL_LEAD', 'ADMINISTRATOR'];
const TABS = [
  ['users', 'Users & roles'],
  ['workspaces', 'Workspaces & repositories'],
  ['config', 'System configuration'],
  ['health', 'Health & monitoring'],
  ['audit', 'Audit & analytics'],
  ['notifications', 'Notifications'],
];
const HEALTH_CHECKS = [
  { name: 'Backend API', path: '/api/auth/csrf' },
  { name: 'Authentication session', path: '/api/auth/me' },
  { name: 'GitHub Integration Service', path: '/api/github/connection' },
];
const STAT_TILES = [
  ['Total users', ''],
  ['Active', '&active=true'],
  ['Disabled', '&active=false'],
  ...SYSTEM_ROLES.map((role) => [role, `&role=${role}`]),
];

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
    updateUser(user, '/status', { active: !user.active },
      `${user.email} ${user.active ? 'disabled' : 'enabled'}.`);
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
        <select aria-label="Filter by role" value={filters.role}
          onChange={(event) => changeFilter('role', event.target.value)}>
          <option value="">All roles</option>
          {SYSTEM_ROLES.map((role) => <option key={role} value={role}>{role}</option>)}
        </select>
        <select aria-label="Filter by status" value={filters.active}
          onChange={(event) => changeFilter('active', event.target.value)}>
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
                      <td>{user.firstName} {user.lastName}<small>@{user.username}</small></td>
                      <td>{user.email}</td>
                      <td>
                        <select
                          aria-label={`Role for ${user.email}`}
                          value={user.role}
                          disabled={isSelf}
                          onChange={(event) => updateUser(user, '/role', { role: event.target.value },
                            `Role of ${user.email} changed to ${event.target.value}.`)}
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

// LD-318: workspaces and repositories
function WorkspaceMembers({ workspaceId }) {
  const { data, error, loading } = useApi(`/api/managed-workspaces/${encodeURIComponent(workspaceId)}/members`);
  return (
    <>
      <h3>Members</h3>
      <Feedback loading={loading} error={error} />
      {data && (data.length === 0 ? <p className="admin-note">No members yet.</p> : (
        <ul className="admin-list">
          {data.map((member) => (
            <li key={member.userId}>{member.displayName || member.username} <small>@{member.username}</small></li>
          ))}
        </ul>
      ))}
    </>
  );
}

function WorkspaceDetail({ workspace, isPersonal }) {
  const repositories = useApi(`/api/workspaces/${encodeURIComponent(workspace.id)}/repositories`);
  const [syncingIds, setSyncingIds] = useState([]);
  const [notice, setNotice] = useState('');
  const [syncError, setSyncError] = useState('');
  const isOwner = workspace.accessRole === 'OWNER';

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

  return (
    <>
      {workspace.description && <p className="admin-note">{workspace.description}</p>}
      <h3>Repositories</h3>
      <Feedback loading={repositories.loading} error={repositories.error || syncError} notice={notice} />
      {repositories.data && (repositories.data.length === 0 ? <p className="admin-note">No repositories connected.</p> : (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr><th>Repository</th><th>Branch</th><th>Visibility</th><th>Status</th><th>Last synced</th>{isOwner && <th>Action</th>}</tr>
            </thead>
            <tbody>
              {repositories.data.map((repository) => (
                <tr key={repository.id}>
                  <td>{repository.fullName}</td>
                  <td>{repository.defaultBranch}</td>
                  <td>{repository.privateRepo ? 'Private' : 'Public'}</td>
                  <td>{repository.status}</td>
                  <td>{formatDate(repository.lastSyncedAt)}</td>
                  {isOwner && (
                    <td>
                      <button type="button" disabled={syncingIds.includes(repository.id)} onClick={() => sync(repository)}>
                        {syncingIds.includes(repository.id) ? 'Syncing…' : 'Sync'}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      {!isPersonal && isOwner && <WorkspaceMembers workspaceId={workspace.id} />}
    </>
  );
}

function WorkspacesPanel({ userId }) {
  const personalId = `ws-${userId}`;
  const { data, error, loading } = useApi('/api/managed-workspaces');
  const [selectedId, setSelectedId] = useState(personalId);
  const workspaces = [{ id: personalId, name: 'Personal workspace', accessRole: 'OWNER' }, ...(data || [])];
  const selected = workspaces.find((workspace) => workspace.id === selectedId) || workspaces[0];

  return (
    <section className="admin-section">
      <h2>Workspaces & repositories</h2>
      <p className="admin-note">
        Lists the workspaces your administrator account owns or belongs to. Workspaces of other users
        are not visible until the backend offers an administrator-wide workspace listing.
      </p>
      <Feedback loading={loading} error={error} />
      <div className="admin-toolbar">
        <select aria-label="Workspace" value={selected.id} onChange={(event) => setSelectedId(event.target.value)}>
          {workspaces.map((workspace) => (
            <option key={workspace.id} value={workspace.id}>{workspace.name} ({workspace.accessRole})</option>
          ))}
        </select>
      </div>
      <WorkspaceDetail key={selected.id} workspace={selected} isPersonal={selected.id === personalId} />
    </section>
  );
}

// LD-319: system configuration (read-only)
function ConfigPanel() {
  const rules = useApi('/api/documentation/drift/severity-rules');
  return (
    <section className="admin-section">
      <h2>System configuration</h2>
      <p className="admin-note">
        Read-only view of the configuration the backend exposes. Changing settings needs a backend
        configuration API, which does not exist yet.
      </p>
      <h3>Frontend runtime</h3>
      <dl className="admin-facts">
        <dt>API base URL</dt><dd>{API_BASE_URL || 'Same origin (proxied)'}</dd>
        <dt>Build mode</dt><dd>{import.meta.env.MODE}</dd>
      </dl>
      <h3>Documentation drift severity rules</h3>
      <Feedback loading={rules.loading} error={rules.error} />
      {rules.data && <pre className="admin-json">{JSON.stringify(rules.data, null, 2)}</pre>}
    </section>
  );
}

// LD-320: system health and monitoring
async function probe(check) {
  const started = performance.now();
  try {
    const response = await fetch(`${API_BASE_URL}${check.path}`, {
      credentials: 'include',
      signal: AbortSignal.timeout(10000),
    });
    return {
      ...check,
      up: response.status < 500,
      detail: `HTTP ${response.status}`,
      ms: Math.round(performance.now() - started),
    };
  } catch {
    return { ...check, up: false, detail: 'No response', ms: null };
  }
}

function HealthPanel() {
  const [state, setState] = useState({ results: [], checkedAt: null, loading: true });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.resolve()
      .then(() => {
        if (cancelled) return [];
        setState((current) => ({ ...current, loading: true }));
        return Promise.all(HEALTH_CHECKS.map(probe));
      })
      .then((results) => {
        if (!cancelled) setState({ results, checkedAt: new Date(), loading: false });
      });
    return () => { cancelled = true; };
  }, [version]);

  return (
    <section className="admin-section">
      <h2>System health</h2>
      <p className="admin-note">
        Checks run from your browser through the backend. The AI service, code analyzer and databases have
        no browser-reachable health endpoint yet, so they are not listed.
      </p>
      <div className="admin-toolbar">
        <button type="button" disabled={state.loading} onClick={() => setVersion((value) => value + 1)}>
          {state.loading ? 'Checking…' : 'Check again'}
        </button>
        {state.checkedAt && <span className="admin-note">Last checked {formatDate(state.checkedAt)}</span>}
      </div>
      {state.results.length > 0 && (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead><tr><th>Service</th><th>Status</th><th>Response</th><th>Detail</th></tr></thead>
            <tbody>
              {state.results.map((result) => (
                <tr key={result.path}>
                  <td>{result.name}</td>
                  <td><span className={`admin-pill ${result.up ? 'up' : 'down'}`}>{result.up ? 'Up' : 'Down'}</span></td>
                  <td>{result.ms === null ? '—' : `${result.ms} ms`}</td>
                  <td>{result.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// LD-321: audit log, analytics and notification configuration
function StatTile({ label, query }) {
  const { data, error } = useApi(`/api/admin/users?size=1${query}`);
  return (
    <div className="admin-stat" title={error || undefined}>
      <span>{label}</span>
      <strong>{error ? '–' : data ? data.totalElements : '…'}</strong>
    </div>
  );
}

function WorkflowHistory({ id }) {
  const { data, error, loading } = useApi(`/api/document-workflows/${encodeURIComponent(id)}/history`);
  return (
    <div className="admin-history">
      <h3>Audit trail</h3>
      <Feedback loading={loading} error={error} />
      {data && (data.length === 0 ? <p className="admin-note">No audit entries.</p> : (
        <ul className="admin-list">
          {data.map((entry) => (
            <li key={entry.id}>
              <strong>{entry.action}</strong>
              {entry.previousStatus || entry.newStatus ? ` · ${entry.previousStatus || '—'} → ${entry.newStatus || '—'}` : ''}
              {' · '}{entry.actorRole || 'user'} {entry.actorUserId}
              {' · '}{formatDate(entry.createdAt)}
              {entry.comment && <small>{entry.comment}</small>}
            </li>
          ))}
        </ul>
      ))}
    </div>
  );
}

function AuditPanel() {
  const [page, setPage] = useState(0);
  const [openId, setOpenId] = useState(null);
  const { data, error, loading } = useApi(`/api/document-workflows/history-accessible?page=${page}&size=10`);

  return (
    <>
      <section className="admin-section">
        <h2>Analytics</h2>
        <div className="admin-stats">
          {STAT_TILES.map(([label, query]) => <StatTile key={label} label={label} query={query} />)}
        </div>
      </section>
      <section className="admin-section">
        <h2>Audit log{data ? ` (${data.totalElements})` : ''}</h2>
        <p className="admin-note">
          Document review workflows and their audit trail. Only roles with document view, review or approval
          permissions can read them, and administrator actions such as role changes are not audited yet.
        </p>
        <Feedback loading={loading} error={error} />
        {data && (data.content || []).length === 0 && <p className="admin-note">No workflows to show.</p>}
        {data && (data.content || []).length > 0 && (
          <>
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead><tr><th>Document</th><th>Status</th><th>Owner</th><th>Updated</th><th>Action</th></tr></thead>
                <tbody>
                  {data.content.map((workflow) => (
                    <tr key={workflow.id}>
                      <td>{workflow.documentTitle || workflow.documentId}</td>
                      <td>{String(workflow.status).replaceAll('_', ' ')}</td>
                      <td>{workflow.ownerUserId}</td>
                      <td>{formatDate(workflow.updatedAt)}</td>
                      <td>
                        <button type="button" onClick={() => setOpenId(openId === workflow.id ? null : workflow.id)}>
                          {openId === workflow.id ? 'Hide history' : 'History'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="admin-pager">
              <button type="button" disabled={data.first} onClick={() => setPage(page - 1)}>Previous</button>
              <span>Page {data.page + 1} of {Math.max(data.totalPages, 1)}</span>
              <button type="button" disabled={data.last} onClick={() => setPage(page + 1)}>Next</button>
            </div>
          </>
        )}
        {openId && <WorkflowHistory key={openId} id={openId} />}
      </section>
    </>
  );
}

export default function AdminDashboard({ userId }) {
  const [tab, setTab] = useState('users');

  return (
    <main className="admin-dashboard">
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
        {tab === 'notifications' && (
          <section className="admin-section">
            <h2>Notification configuration</h2>
            <NotificationPreferences />
          </section>
        )}
      </div>
    </main>
  );
}



