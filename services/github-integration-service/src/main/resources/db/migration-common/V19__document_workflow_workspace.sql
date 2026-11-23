-- Workflows belong to a workspace so that reviewers and approvers only reach documents of workspaces they
-- belong to. Existing rows were created in the personal workspace of their owner.
ALTER TABLE document_workflows ADD COLUMN workspace_id VARCHAR(100);
UPDATE document_workflows SET workspace_id = 'ws-' || owner_user_id WHERE workspace_id IS NULL;
CREATE INDEX idx_document_workflows_workspace ON document_workflows (workspace_id);
