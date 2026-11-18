import { useEffect, useState } from 'react';
import { githubApi } from './githubApi';
import PageFrame from './rbac/PageFrame';
import { usePermission } from './rbac/usePermission';
import './DocumentationCollections.css';

function WorkspacePicker({ userId }) {
  const personalId = `ws-${userId}`;
  const [workspace, setWorkspace] = useState(personalId);
  const [workspaces, setWorkspaces] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    let current = true;
    githubApi('/api/managed-workspaces')
      .then((items) => { if (current) setWorkspaces(items); })
      .catch((failure) => { if (current) setError(failure.message); });
    return () => { current = false; };
  }, []);

  return (
    <>
      <label className="collection-field">
        Workspace
        <select value={workspace} onChange={(event) => setWorkspace(event.target.value)}>
          <option value={personalId}>Personal workspace</option>
          {workspaces.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
      </label>
      {error && <p role="alert" className="documentation-error">{error}</p>}
      <WorkspaceCollections key={workspace} workspace={workspace} personalUserId={workspace === personalId ? userId : null} />
    </>
  );
}

function WorkspaceCollections({ workspace, personalUserId }) {
  const { can } = usePermission();
  const canCreate = can('collections', 'C');
  const canUpdate = can('collections', 'U');
  const canDelete = can('collections', 'D');
  const workspacePath = `/api/workspaces/${encodeURIComponent(workspace)}`;
  const path = `${workspacePath}/collections`;
  const [collections, setCollections] = useState(null);
  const [repositories, setRepositories] = useState(null);
  const [owners, setOwners] = useState([]);
  const [openId, setOpenId] = useState(null);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [setupError, setSetupError] = useState('');
  const [notice, setNotice] = useState('');
  const selected = collections?.find((item) => item.id === openId);

  useEffect(() => {
    let current = true;
    githubApi(path)
      .then((data) => { if (current) setCollections(data); })
      .catch((failure) => { if (current) setError(failure.message); });
    if (canCreate || canUpdate) {
      githubApi(`${workspacePath}/repositories`)
        .then((data) => {
          if (current) setRepositories(data.filter((item) => item.status !== 'DISCONNECTED'));
        })
        .catch((failure) => { if (current) setSetupError(failure.message); });
    }
    if (canUpdate) {
      const candidates = personalUserId
        ? Promise.resolve([{ userId: personalUserId, displayName: 'You' }])
        : githubApi(`/api/managed-workspaces/${encodeURIComponent(workspace)}/collection-owner-candidates`);
      candidates
        .then((data) => { if (current) setOwners(data); })
        .catch((failure) => { if (current) setSetupError(failure.message); });
    }
    return () => { current = false; };
  }, [path, workspacePath, workspace, canCreate, canUpdate, personalUserId]);

  async function edit() {
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const items = await githubApi(path);
      setCollections(items);
      if (items.some((item) => item.id === openId)) {
        setEditing(true);
      } else {
        setOpenId(null);
        setError('This collection is no longer available.');
      }
    } catch (failure) {
      setError(failure.message);
    } finally {
      setSaving(false);
    }
  }

  async function save(body) {
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const item = await githubApi(selected ? `${path}/${selected.id}` : path, {
        method: selected ? 'PUT' : 'POST', body,
      });
      setCollections((items) => [...items.filter((entry) => entry.id !== item.id), item]
        .sort((left, right) => left.name.localeCompare(right.name)));
      setOpenId(item.id);
      setEditing(false);
      setNotice(selected ? 'Collection updated.' : 'Collection created.');
    } catch (failure) {
      setError(failure.message);
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!window.confirm(`Permanently delete “${selected.name}” and its document links? The documents and owner assignments will be kept.`)) return;
    setSaving(true);
    setError('');
    setNotice('');
    try {
      await githubApi(`${path}/${selected.id}`, { method: 'DELETE' });
      setCollections((items) => items.filter((item) => item.id !== selected.id));
      setOpenId(null);
      setEditing(false);
      setNotice('Collection deleted.');
    } catch (failure) {
      setError(failure.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      {error && <p role="alert" className="documentation-error">{error}</p>}
      {setupError && <p role="alert" className="documentation-error">{setupError}</p>}
      {notice && <p role="status">{notice}</p>}
      {!collections && !error && <p role="status">Loading collections…</p>}
      {collections && (
        <section className="collection-panel" aria-label="Collections">
          <div className="collection-toolbar">
            <h2>Collections</h2>
            {canCreate && repositories && (
              <button type="button" disabled={saving} onClick={() => {
                setOpenId(null);
                setEditing(true);
                setError('');
                setNotice('');
              }}>New collection</button>
            )}
          </div>
          {collections.length === 0 && !editing && <p>No collections yet.</p>}
          {collections.length > 0 && (
            <ul className="collection-list" aria-label="Available collections">
              {collections.map((item) => (
                <li key={item.id}>
                  <button type="button" className="documentation-secondary-button" disabled={saving}
                    aria-pressed={item.id === openId} onClick={() => {
                      setOpenId(item.id);
                      setEditing(false);
                      setError('');
                      setNotice('');
                    }}>
                    {item.name}
                  </button>
                  {item.repositoryName && <small>{item.repositoryName}</small>}
                </li>
              ))}
            </ul>
          )}
          {editing && (
            <CollectionForm key={openId || 'new'} collection={selected} repositories={repositories}
              saving={saving} onSave={save} onCancel={() => setEditing(false)} />
          )}
          {selected && !editing && (
            <>
              <h3>{selected.name}</h3>
              <p>{selected.repositoryName || 'No connected repository'}</p>
              {selected.description && <p>{selected.description}</p>}
              <div className="collection-toolbar">
                {canUpdate && repositories && (
                  <button type="button" disabled={saving} onClick={edit}>Edit collection</button>
                )}
                {canDelete && <button type="button" disabled={saving} onClick={remove}>Delete collection</button>}
              </div>
              <CollectionDocuments key={selected.id} path={`${path}/${selected.id}`}
                canUpdate={canUpdate} owners={owners} hasRepository={Boolean(selected.repositoryName)} />
            </>
          )}
        </section>
      )}
    </>
  );
}

function CollectionForm({ collection, repositories, saving, onSave, onCancel }) {
  const repositoryLocked = Boolean(collection?.hasDocuments);
  const repositoryId = collection?.repositoryId || '';
  const repositoryUnavailable = repositoryId && !repositories.some((item) => item.id === repositoryId);

  function submit(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    onSave({
      name: form.get('name').trim(),
      description: form.get('description').trim() || null,
      repositoryId: repositoryLocked ? collection.repositoryId : form.get('repository') || null,
    });
  }

  return (
    <form className="template-form" onSubmit={submit}>
      <h2>{collection ? 'Edit collection' : 'New collection'}</h2>
      <fieldset disabled={saving}>
        <label>Name <input name="name" required maxLength={120} defaultValue={collection?.name} /></label>
        <label>Description <textarea name="description" maxLength={1000} defaultValue={collection?.description || ''} /></label>
        <label className="collection-field">
          Repository
          <select name="repository" defaultValue={repositoryId} disabled={repositoryLocked}
            aria-describedby={repositoryLocked ? 'collection-repository-lock' : undefined}>
            <option value="">No repository</option>
            {repositoryUnavailable && <option value={repositoryId}>Unavailable repository</option>}
            {repositories.map((item) => <option key={item.id} value={item.id}>{item.fullName}</option>)}
          </select>
        </label>
        {repositoryLocked && <p id="collection-repository-lock">Remove all documents from this collection to change its repository.</p>}
      </fieldset>
      <div className="collection-toolbar">
        <button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save collection'}</button>
        <button type="button" disabled={saving} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

function CollectionDocuments({ path, canUpdate, owners, hasRepository }) {
  const [documents, setDocuments] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [candidate, setCandidate] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [revision, setRevision] = useState(0);
  const available = candidates.filter((item) => !documents?.some((document) => document.id === item.id));

  useEffect(() => {
    let current = true;
    githubApi(`${path}/documents`)
      .then((items) => { if (current) setDocuments(items); })
      .catch((failure) => { if (current) setError(failure.message); });
    if (canUpdate && hasRepository) {
      githubApi(`${path}/document-candidates`)
        .then((items) => { if (current) setCandidates(items); })
        .catch((failure) => { if (current) setError(failure.message); });
    }
    return () => { current = false; };
  }, [path, canUpdate, hasRepository, revision]);

  async function mutate(suffix, method, success) {
    setPending(true);
    setError('');
    setNotice('');
    try {
      await githubApi(`${path}/documents/${suffix}`, { method });
      setCandidate('');
      setDocuments(null);
      setRevision((value) => value + 1);
      setNotice(success);
    } catch (failure) {
      setError(failure.message);
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="collection-panel" aria-label="Collection documents">
      <h4>Documents</h4>
      {error && <p role="alert" className="documentation-error">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {!documents && !error && <p role="status">Loading documents…</p>}
      {documents?.length === 0 && <p>No documents in this collection.</p>}
      {documents && canUpdate && available.length > 0 && (
        <form className="collection-toolbar" onSubmit={(event) => {
          event.preventDefault();
          if (candidate) mutate(candidate, 'PUT', 'Document added.');
        }}>
          <label className="collection-field">
            Add document
            <select value={candidate} disabled={pending} onChange={(event) => setCandidate(event.target.value)}>
              <option value="">Select a document</option>
              {available.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
            </select>
          </label>
          <button type="submit" disabled={pending || !candidate}>Add to collection</button>
        </form>
      )}
      {documents?.length > 0 && (
        <ul className="collection-documents">
          {documents.map((item) => (
            <li key={item.id}>
              <strong>{item.title}</strong>
              <p>{item.assignedOwnerId
                ? `Owner #${item.assignedOwnerId}`
                : 'Unassigned'}</p>
              {canUpdate && (
                <div className="collection-toolbar">
                  <OwnerForm key={item.assignedOwnerId || 'unassigned'} document={item} owners={owners}
                    pending={pending} onSave={(target) => mutate(
                      target ? `${item.id}/owner/${encodeURIComponent(target)}` : `${item.id}/owner`,
                      target ? 'PUT' : 'DELETE', target ? 'Owner assigned.' : 'Owner cleared.',
                    )} />
                  <button type="button" disabled={pending} aria-label={`Remove ${item.title} from collection`}
                    onClick={() => mutate(item.id, 'DELETE', 'Document removed from collection.')}>Remove</button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function OwnerForm({ document, owners, pending, onSave }) {
  const assigned = document.assignedOwnerId || '';
  const [target, setTarget] = useState(assigned);
  const hasAssignedOption = owners.some((owner) => String(owner.userId) === assigned);
  return (
    <form className="collection-toolbar" onSubmit={(event) => {
      event.preventDefault();
      if (target !== assigned) onSave(target);
    }}>
      <label className="collection-field">
        Document owner
        <select value={target} disabled={pending} onChange={(event) => setTarget(event.target.value)}>
          <option value="">Unassigned</option>
          {assigned && !hasAssignedOption && <option value={assigned}>Current owner #{assigned}</option>}
          {owners.map((owner) => (
            <option key={owner.userId} value={owner.userId}>
              {owner.displayName || owner.username || `User #${owner.userId}`}
            </option>
          ))}
        </select>
      </label>
      <button type="submit" disabled={pending || target === assigned}>Save owner</button>
    </form>
  );
}

export default function DocumentationCollections({ userId }) {
  return (
    <PageFrame title="Documentation Collections" className="documentation-page collections-page">
      <WorkspacePicker key={userId} userId={userId} />
    </PageFrame>
  );
}
