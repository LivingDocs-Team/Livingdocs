import { useState } from 'react';
import {
  SECTION_HINTS,
  SECTION_NAMES,
  createTemplate,
  deleteTemplate,
  updateTemplate,
} from './templateApi';

/** Radio cards to choose a template, with the selected template's details underneath. */
export function TemplatePicker({ templates, value, onChange, isLoading, loadError, disabled }) {
  const selected = templates.find((item) => item.id === value);

  return (
    <>
      {isLoading && <p className="documentation-hint" role="status">Loading templates…</p>}
      {loadError && <p className="documentation-hint">{loadError}</p>}

      <div className="documentation-template-list" role="radiogroup" aria-label="Documentation template">
        {templates.map((item) => (
          <label
            key={item.id}
            className={`documentation-template ${value === item.id ? 'selected' : ''}`}
          >
            <input
              type="radio"
              name="documentation-template"
              value={item.id}
              checked={value === item.id}
              disabled={disabled}
              onChange={() => onChange(item.id)}
            />
            <span>
              <strong>
                {item.name}
                <em className={`template-badge ${item.built_in ? 'built-in' : 'custom'}`}>
                  {item.built_in ? 'Built-in' : 'Custom'}
                </em>
              </strong>
              {item.description && <small>{item.description}</small>}
              <small className="template-sections">{item.sections.join(' → ')}</small>
            </span>
          </label>
        ))}
      </div>

      {selected ? (
        <div className="template-details" aria-label="Selected template details">
          <p>
            <strong>Sections in every file:</strong> {selected.sections.join(', ')}
          </p>
          <p>
            <strong>Writing instructions:</strong> {selected.instructions}
          </p>
        </div>
      ) : (
        <p className="documentation-error" role="alert">
          The selected template is no longer available. Choose another template.
        </p>
      )}
    </>
  );
}

const EMPTY_FORM = { name: '', description: '', instructions: '', sections: ['Overview'] };

function toForm(template) {
  return {
    name: template.name,
    description: template.description || '',
    instructions: template.instructions,
    sections: [...template.sections],
  };
}

/** Create, edit and delete custom templates. Built-in templates are read-only. */
export function TemplateManager({ templates, onSaved, onDeleted }) {
  const [editingId, setEditingId] = useState(null); // null | 'new' | template id
  const [form, setForm] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState('');
  const [notice, setNotice] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState('');

  const custom = templates.filter((item) => !item.built_in);

  function startNew() {
    setEditingId('new');
    setForm(EMPTY_FORM);
    setFormError('');
    setNotice('');
  }

  function startEdit(template) {
    setEditingId(template.id);
    setForm(toForm(template));
    setFormError('');
    setNotice('');
  }

  function cancel() {
    setEditingId(null);
    setFormError('');
  }

  function toggleSection(section) {
    setForm((current) => ({
      ...current,
      sections: current.sections.includes(section)
        ? current.sections.filter((item) => item !== section)
        : [...current.sections, section],
    }));
  }

  function moveSection(index, step) {
    setForm((current) => {
      const sections = [...current.sections];
      const target = index + step;
      if (target < 0 || target >= sections.length) return current;
      [sections[index], sections[target]] = [sections[target], sections[index]];
      return { ...current, sections };
    });
  }

  async function handleSave(event) {
    event.preventDefault();
    const body = {
      name: form.name.trim(),
      description: form.description.trim(),
      instructions: form.instructions.trim(),
      sections: form.sections,
    };
    if (!body.name || !body.instructions) {
      setFormError('Enter a name and writing instructions for the template.');
      return;
    }
    if (body.sections.length === 0) {
      setFormError('Choose at least one section.');
      return;
    }

    setIsSaving(true);
    setFormError('');
    try {
      const saved = editingId === 'new'
        ? await createTemplate(body)
        : await updateTemplate(editingId, body);
      setNotice(`Template "${saved.name}" saved.`);
      setEditingId(null);
      onSaved(saved);
    } catch (requestError) {
      setFormError(requestError.message || 'Could not save the template.');
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDelete(template) {
    if (confirmDeleteId !== template.id) {
      setConfirmDeleteId(template.id);
      return;
    }
    setConfirmDeleteId('');
    setFormError('');
    try {
      await deleteTemplate(template.id);
      setNotice(`Template "${template.name}" deleted.`);
      if (editingId === template.id) setEditingId(null);
      onDeleted(template);
    } catch (requestError) {
      setFormError(requestError.message || 'Could not delete the template.');
    }
  }

  return (
    <section className="template-manager" aria-labelledby="template-manager-title">
      <div className="template-manager-header">
        <h2 id="template-manager-title">Manage templates</h2>
        <button type="button" onClick={startNew} disabled={isSaving}>New template</button>
      </div>
      <p className="documentation-hint">
        Built-in templates are read-only. Custom templates are shared by everyone in this LivingDocs installation.
      </p>

      {custom.length === 0 ? (
        <p className="documentation-hint">No custom templates yet.</p>
      ) : (
        <ul className="template-manager-list">
          {custom.map((item) => (
            <li key={item.id}>
              <span>
                <strong>{item.name}</strong>
                <small>{item.sections.join(' → ')}</small>
              </span>
              <span className="template-manager-actions">
                <button
                  type="button"
                  className="documentation-secondary-button"
                  onClick={() => startEdit(item)}
                  aria-label={`Edit ${item.name}`}
                >
                  Edit
                </button>
                <button
                  type="button"
                  className="documentation-secondary-button template-delete"
                  onClick={() => handleDelete(item)}
                  aria-label={confirmDeleteId === item.id ? `Confirm delete ${item.name}` : `Delete ${item.name}`}
                >
                  {confirmDeleteId === item.id ? 'Confirm delete' : 'Delete'}
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}

      {notice && <p className="documentation-notice" role="status">{notice}</p>}
      {formError && <p className="documentation-error" role="alert">{formError}</p>}

      {editingId && (
        <form className="template-form" onSubmit={handleSave}>
          <h3>{editingId === 'new' ? 'New template' : 'Edit template'}</h3>

          <label htmlFor="template-name">Name</label>
          <input
            id="template-name"
            value={form.name}
            maxLength={80}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
            required
          />

          <label htmlFor="template-description">Description</label>
          <input
            id="template-description"
            value={form.description}
            maxLength={300}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
          />

          <fieldset className="template-section-picker">
            <legend>Sections</legend>
            {SECTION_NAMES.map((section) => (
              <label key={section}>
                <input
                  type="checkbox"
                  checked={form.sections.includes(section)}
                  onChange={() => toggleSection(section)}
                />
                {section} <small>{SECTION_HINTS[section]}</small>
              </label>
            ))}
          </fieldset>

          {form.sections.length > 0 && (
            <ol className="template-section-order" aria-label="Section order">
              {form.sections.map((section, index) => (
                <li key={section}>
                  <span>{section}</span>
                  <button
                    type="button"
                    className="documentation-secondary-button"
                    onClick={() => moveSection(index, -1)}
                    disabled={index === 0}
                    aria-label={`Move ${section} up`}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className="documentation-secondary-button"
                    onClick={() => moveSection(index, 1)}
                    disabled={index === form.sections.length - 1}
                    aria-label={`Move ${section} down`}
                  >
                    ↓
                  </button>
                </li>
              ))}
            </ol>
          )}

          <label htmlFor="template-instructions">Writing instructions for the AI</label>
          <textarea
            id="template-instructions"
            rows={4}
            maxLength={4000}
            value={form.instructions}
            placeholder="For example: explain each function in one sentence for new team members."
            onChange={(event) => setForm({ ...form, instructions: event.target.value })}
            required
          />

          <div className="documentation-actions">
            <button type="submit" disabled={isSaving}>
              {isSaving ? 'Saving…' : 'Save template'}
            </button>
            <button type="button" className="documentation-secondary-button" onClick={cancel}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
