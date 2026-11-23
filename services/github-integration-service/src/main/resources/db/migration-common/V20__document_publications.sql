-- A publication is the fact that GitHub confirmed a commit of an approved document version. It is recorded
-- separately from the review workflow, whose status stays APPROVED. One row per workflow and version.
CREATE TABLE document_publications (
    id UUID PRIMARY KEY,
    workflow_id UUID NOT NULL REFERENCES document_workflows (id),
    document_id VARCHAR(64) NOT NULL,
    version INTEGER NOT NULL,
    repository_id UUID NOT NULL,
    branch VARCHAR(255) NOT NULL,
    path VARCHAR(500) NOT NULL,
    commit_sha VARCHAR(64) NOT NULL,
    published_at TIMESTAMP WITH TIME ZONE NOT NULL,
    published_by VARCHAR(100) NOT NULL,
    CONSTRAINT uq_document_publications_workflow_version UNIQUE (workflow_id, version)
);
CREATE INDEX idx_document_publications_document ON document_publications (document_id);
