import { TemplateManager } from './DocumentationTemplates';
import PageFrame from './rbac/PageFrame';
import { useTemplates } from './templateApi';

/** Standalone page for the existing template manager (Documentation Templates, matrix row #22). */
export default function TemplateLibrary({ userId }) {
  const templateList = useTemplates(userId);
  return (
    <PageFrame
      title="Documentation Templates"
      titleId="template-library-title"
      className="documentation-page"
      subtitle="Create, edit and delete the templates used for documentation generation."
    >
      {templateList.isLoading && <p role="status">Loading templates…</p>}
      {templateList.loadError && <p className="documentation-error" role="alert">{templateList.loadError}</p>}
      <TemplateManager
        templates={templateList.templates}
        onSaved={() => templateList.reload()}
        onDeleted={() => templateList.reload()}
      />
    </PageFrame>
  );
}
