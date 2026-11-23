import { TemplateManager } from './DocumentationTemplates';
import PageFrame from './rbac/PageFrame';
import { usePermission } from './rbac/usePermission';
import { useTemplates } from './templateApi';
import './InsightScreens.css';

/** Read-only list of every template: roles without the create/edit/delete rights only browse. */
function TemplateCatalog({ templates }) {
  if (templates.length === 0) return <p className="documentation-hint">No templates are available yet.</p>;
  return (
    <ul className="template-catalog" aria-label="Documentation templates">
      {templates.map((item) => (
        <li key={item.id} className="template-catalog-item">
          <details>
            <summary>
              <strong>{item.name}</strong>
              <span className="insight-tag">{item.built_in ? 'Built-in' : 'Custom'}</span>
            </summary>
            {item.description && <p>{item.description}</p>}
            {item.sections?.length > 0 && <p><small>Sections: {item.sections.join(' → ')}</small></p>}
            {item.instructions && <pre>{item.instructions}</pre>}
          </details>
        </li>
      ))}
    </ul>
  );
}

/** Documentation Templates (matrix row #22): roles that manage templates edit them, everyone else browses. */
export default function TemplateLibrary({ userId }) {
  const templateList = useTemplates(userId);
  const { can } = usePermission();
  const canManage = can('templates', 'C') || can('templates', 'U') || can('templates', 'D');
  return (
    <PageFrame
      title={canManage ? 'Documentation Templates' : 'Template Library'}
      titleId="template-library-title"
      className="documentation-page"
      subtitle={canManage
        ? 'Create, edit and delete the templates used for documentation generation.'
        : 'Browse the templates available for documentation generation.'}
    >
      {templateList.isLoading && <p role="status">Loading templates…</p>}
      {templateList.loadError && <p className="documentation-error" role="alert">{templateList.loadError}</p>}
      {canManage ? (
        <TemplateManager
          templates={templateList.templates}
          onSaved={() => templateList.reload()}
          onDeleted={() => templateList.reload()}
        />
      ) : (
        !templateList.isLoading && !templateList.loadError && <TemplateCatalog templates={templateList.templates} />
      )}
    </PageFrame>
  );
}
