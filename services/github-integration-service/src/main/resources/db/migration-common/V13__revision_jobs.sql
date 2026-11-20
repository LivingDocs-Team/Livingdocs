CREATE TABLE revision_jobs (
    id                  UUID PRIMARY KEY,
    repository_id       UUID NOT NULL REFERENCES repositories (id) ON DELETE CASCADE,
    trigger_type        VARCHAR(20) NOT NULL,
    commit_sha          VARCHAR(40) NOT NULL,
    pr_number           INTEGER NOT NULL,
    status              VARCHAR(16) NOT NULL,
    attempts            INTEGER NOT NULL DEFAULT 0,
    available_at        TIMESTAMP WITH TIME ZONE NOT NULL,
    lease_token         UUID,
    error_code          VARCHAR(50),
    CONSTRAINT uq_revision_job UNIQUE (repository_id, trigger_type, commit_sha, pr_number)
);

CREATE INDEX idx_revision_jobs_available ON revision_jobs (status, available_at);
