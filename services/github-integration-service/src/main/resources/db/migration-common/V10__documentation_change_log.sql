CREATE TABLE IF NOT EXISTS documentation_change_logs (
    id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL,
    repository_id UUID,
    version_number INTEGER,
    action VARCHAR(64) NOT NULL,
    summary VARCHAR(500) NOT NULL,
    actor_id VARCHAR(128),
    actor_name VARCHAR(255),
    actor_role VARCHAR(64) NOT NULL,
    trigger_source VARCHAR(64) NOT NULL,
    status VARCHAR(64) NOT NULL,
    reference_id VARCHAR(128),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_doc_changelog_doc_created
    ON documentation_change_logs (document_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_doc_changelog_repo_created
    ON documentation_change_logs (repository_id, created_at DESC);